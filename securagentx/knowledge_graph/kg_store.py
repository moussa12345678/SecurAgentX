"""SecurAgentX Knowledge Graph — networkx-backed graph store with 7 search types.

This module provides a self-contained, synchronous, dependency-light knowledge
graph for VulnAgent. It mirrors the seven search strategies exposed by
Graphiti/SecurAgentX's ``graphiti_search`` tool:

    1. ``search_temporal``              — time-bounded retrieval
    2. ``search_entity_relationships``  — BFS from a center node
    3. ``search_diverse``               — MMR-reranked diverse retrieval
    4. ``search_episode_context``       — episodic memory of agent/tool runs
    5. ``search_successful_tools``      — proven successful tool executions
    6. ``search_recent_context``        — recency-bounded context window
    7. ``search_entity_by_label``       — label-filtered entity inventory

Design
------
* Backed by a ``networkx.DiGraph`` (lazy-imported so the module is import-safe
  even if networkx is unexpectedly absent — the import error is surfaced on
  first use, not at module load).
* Optional Neo4j backend via lazy import: if ``neo4j`` is installed and a
  ``neo4j_uri`` is provided, writes/reads are mirrored to Neo4j. Otherwise
  networkx is the sole source of truth.
* Nodes carry a ``type`` attribute (``entity`` | ``observation`` | ``message``
  | ``episode``) plus ``label``, ``entity_type`` (for entities), ``created_at``,
  and any user-supplied properties.
* Edges carry a ``type`` attribute (``relationship`` | ``mentions`` |
  ``references`` | the user-supplied ``rel_type``) plus ``created_at``.
* Thread-safe via a single ``threading.RLock``.
* Persistence: JSON (default) or GraphML. Default path:
  ``~/.securagentx/data/knowledge_graph.json``.

All search methods return formatted human-readable strings suitable for
consumption by an LLM agent. Raw dict results are also available via the
``*_raw`` companions where useful.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("securagentx.knowledge_graph.kg_store")

# ──────────────────────────────────────────────────────────────────────────────
# Defaults & allowed values (mirror the original graphiti_search.go)
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_TEMPORAL_MAX_RESULTS = 15
DEFAULT_RECENT_MAX_RESULTS = 10
DEFAULT_SUCCESSFUL_MAX_RESULTS = 15
DEFAULT_EPISODE_MAX_RESULTS = 10
DEFAULT_RELATIONSHIP_MAX_RESULTS = 20
DEFAULT_DIVERSE_MAX_RESULTS = 10
DEFAULT_LABEL_MAX_RESULTS = 25

DEFAULT_MAX_DEPTH = 2
DEFAULT_DIVERSITY_LEVEL = "medium"
DEFAULT_RECENCY_WINDOW = "24h"

MAX_ALLOWED_DEPTH = 3

ALLOWED_RECENCY_WINDOWS = {"1h", "6h", "24h", "7d"}
ALLOWED_DIVERSITY_LEVELS = {"low", "medium", "high"}

# MMR λ per diversity level. λ=1 → pure relevance; λ=0 → pure diversity.
DIVERSITY_LAMBDA: Dict[str, float] = {
    "low": 0.7,
    "medium": 0.5,
    "high": 0.3,
}

RECENCY_WINDOW_DELTA: Dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}

DEFAULT_PERSISTENCE_PATH = Path("~/.securagentx/data/knowledge_graph.json").expanduser()

# Node "type" tags
NODE_TYPE_ENTITY = "entity"
NODE_TYPE_OBSERVATION = "observation"
NODE_TYPE_MESSAGE = "message"
NODE_TYPE_EPISODE = "episode"

# Edge "type" tags
EDGE_TYPE_RELATIONSHIP = "relationship"
EDGE_TYPE_MENTIONS = "mentions"
EDGE_TYPE_REFERENCES = "references"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _now() -> datetime:
    """UTC now as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_dt(value: Any) -> Optional[datetime]:
    """Parse a datetime from ISO string, epoch float, or datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Try ISO first
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
        # Try common alternative formats
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
    return None


_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _tokenize(text: str) -> List[str]:
    """Lowercase + split on non-alphanumeric (preserving _)."""
    if not text:
        return []
    return _TOKEN_RE.findall(text.lower())


def _jaccard_similarity(a: Iterable[str], b: Iterable[str]) -> float:
    sa = set(a)
    sb = set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _mmr_select(
    candidates: List[Tuple[str, float, Dict[str, Any]]],
    max_results: int,
    lambda_: float,
) -> List[Dict[str, Any]]:
    """Maximal Marginal Relevance selection.

    ``candidates`` is a list of ``(node_id, relevance_score, node_data)``
    tuples, pre-sorted by descending relevance. Returns the selected
    ``node_data`` dicts.
    """
    if not candidates:
        return []
    if max_results <= 0:
        return []

    selected: List[Tuple[str, float, Dict[str, Any]]] = []
    remaining = list(candidates)

    while remaining and len(selected) < max_results:
        best: Optional[Tuple[str, float, Dict[str, Any]]] = None
        best_score = -math.inf
        best_idx = -1
        for idx, (nid, rel, data) in enumerate(remaining):
            if not selected:
                diversity = 1.0
            else:
                # Max similarity to any already-selected item (Jaccard on tokens)
                new_tokens = _tokenize(data.get("summary") or data.get("label") or "")
                diversity = max(
                    _jaccard_similarity(
                        new_tokens,
                        _tokenize(s.get("summary") or s.get("label") or ""),
                    )
                    for _, _, s in selected
                ) if new_tokens else 0.0
            score = lambda_ * rel - (1.0 - lambda_) * diversity
            if score > best_score:
                best_score = score
                best = (nid, rel, data)
                best_idx = idx
        if best is None:
            break
        selected.append(best)
        remaining.pop(best_idx)
    return [d for _, _, d in selected]


# ──────────────────────────────────────────────────────────────────────────────
# KnowledgeGraph
# ──────────────────────────────────────────────────────────────────────────────


class KnowledgeGraph:
    """Synchronous networkx-backed knowledge graph with 7 search types.

    Parameters
    ----------
    persistence_path:
        Optional path to a JSON file used for ``save()`` / ``load()``. If
        provided and the file exists at construction time, it is loaded
        automatically.
    neo4j_uri:
        Optional Neo4j connection URI. If provided AND the ``neo4j`` Python
        driver is installed, writes/reads mirror to Neo4j. Otherwise the
        Neo4j backend is silently skipped (networkx remains source of truth).
    """

    def __init__(
        self,
        persistence_path: Optional[str] = None,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
    ) -> None:
        # Lazy-import networkx so the module is import-safe without it
        try:
            import networkx as nx  # type: ignore
        except ImportError as exc:  # pragma: no cover — networkx is a hard dep
            raise ImportError(
                "SecurAgentX KnowledgeGraph requires the 'networkx' package. "
                "Install it with: pip install networkx"
            ) from exc

        self._nx = nx
        self._graph = nx.DiGraph()
        self._lock = threading.RLock()

        # Persistence path resolution
        if persistence_path is None:
            self._persistence_path: Optional[Path] = DEFAULT_PERSISTENCE_PATH
        else:
            self._persistence_path = Path(persistence_path).expanduser()

        # Optional Neo4j backend (lazy)
        self._neo4j_uri = neo4j_uri
        self._neo4j_user = neo4j_user
        self._neo4j_password = neo4j_password
        self._neo4j_driver = None
        self._init_neo4j()

        # Auto-load existing persistence file
        if self._persistence_path is not None and self._persistence_path.exists():
            try:
                self.load(str(self._persistence_path))  # type: ignore[arg-type]  # type: ignore[assignment]
                logger.debug("KG loaded from %s", self._persistence_path)
            except Exception as exc:  # noqa: BLE001 — logged
                logger.warning("KG load from %s failed: %s", self._persistence_path, exc)

    # ── Neo4j backend ──────────────────────────────────────────────────────

    def _init_neo4j(self) -> None:
        """Attempt to connect to Neo4j if configured and available."""
        if not self._neo4j_uri:
            return
        try:
            from neo4j import GraphDatabase  # type: ignore
        except ImportError:
            logger.info("neo4j driver not installed — falling back to networkx only")
            return
        try:
            self._neo4j_driver = GraphDatabase.driver(
                self._neo4j_uri,
                auth=(self._neo4j_user or "", self._neo4j_password or ""),
            )
            logger.info("Neo4j backend connected at %s", self._neo4j_uri)
        except Exception as exc:  # noqa: BLE001 — logged
            logger.warning("Neo4j connection failed: %s — using networkx only", exc)
            self._neo4j_driver = None

    @property
    def has_neo4j(self) -> bool:
        return self._neo4j_driver is not None

    # ── Internal helpers ───────────────────────────────────────────────────

    def _new_id(self, prefix: str = "n") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:16]}"

    def _node_exists(self, node_id: str) -> bool:
        return self._graph.has_node(node_id)

    def _find_entity_by_label(self, label: str) -> Optional[str]:
        """Return the node_id of the first entity node with matching label."""
        if not label:
            return None
        target = label.strip().lower()
        for nid, data in self._graph.nodes(data=True):
            if data.get("type") != NODE_TYPE_ENTITY:
                continue
            lbl = data.get("label", "")
            if lbl and lbl.strip().lower() == target:
                return nid
        # Fuzzy fallback: substring match
        for nid, data in self._graph.nodes(data=True):
            if data.get("type") != NODE_TYPE_ENTITY:
                continue
            lbl = data.get("label", "")
            if lbl and target in lbl.lower():
                return nid
        return None

    def _format_node(self, nid: str, depth: int = 0) -> str:
        """Format a single node as a readable string."""
        data = self._graph.nodes[nid]
        ntype = data.get("type", "node")
        label = data.get("label", nid)
        summary = data.get("summary", "")
        created = data.get("created_at", "")
        indent = "  " * depth
        lines = [f"{indent}- [{ntype}] {label}"]
        if summary:
            lines.append(f"{indent}  summary: {summary}")
        # Show key properties (excluding internal bookkeeping)
        skip = {"type", "label", "summary", "created_at", "node_id"}
        props = {k: v for k, v in data.items() if k not in skip and not k.startswith("_")}
        if props:
            prop_str = ", ".join(f"{k}={v!r}" for k, v in props.items())
            lines.append(f"{indent}  props: {prop_str}")
        if created:
            lines.append(f"{indent}  created_at: {created}")
        return "\n".join(lines)

    def _format_edge(self, u: str, v: str, key_or_data: Any) -> str:
        if isinstance(key_or_data, dict):
            edata = key_or_data
        else:
            edata = self._graph.get_edge_data(u, v) or {}
        etype = edata.get("type", "relationship")
        fact = edata.get("fact") or edata.get("summary") or ""
        u_label = self._graph.nodes[u].get("label", u)
        v_label = self._graph.nodes[v].get("label", v)
        base = f"  --[{etype}]--> {u_label} → {v_label}"
        if fact:
            base += f"  ({fact})"
        return base

    # ── Add methods ─────────────────────────────────────────────────────────

    def add_entity(
        self,
        label: str,
        entity_type: str = "entity",
        properties: Optional[dict] = None,
    ) -> str:
        """Add an entity node. Returns the node_id.

        If an entity with the same label already exists, its properties are
        merged (existing keys are preserved unless overwritten by ``properties``).
        """
        if not label:
            raise ValueError("entity label must be non-empty")
        with self._lock:
            existing = self._find_entity_by_label(label)
            props = dict(properties or {})
            if existing is not None:
                # Merge
                data = self._graph.nodes[existing]
                for k, v in props.items():
                    if k not in data:
                        data[k] = v
                # Always update entity_type if new info
                if entity_type and "entity_type" not in data:
                    data["entity_type"] = entity_type
                data.setdefault("updated_at", _iso(_now()))
                self._mirror_neo4j_upsert_node(existing)
                return existing

            node_id = self._new_id("ent")
            data = {
                "type": NODE_TYPE_ENTITY,
                "label": str(label),
                "entity_type": str(entity_type or "entity"),
                "summary": props.pop("summary", ""),
                "created_at": _iso(_now()),
                "node_id": node_id,
            }
            # Remaining properties stored as-is
            for k, v in props.items():
                if k not in data:
                    data[k] = v
            self._graph.add_node(node_id, **data)
            self._mirror_neo4j_upsert_node(node_id)
            logger.debug("KG add_entity: %s (%s) → %s", label, entity_type, node_id)
            return node_id

    def add_relationship(
        self,
        source: str,
        target: str,
        rel_type: str = "related_to",
        properties: Optional[dict] = None,
    ) -> Tuple[str, str]:
        """Add a directed edge between two nodes.

        ``source`` / ``target`` may be either node_ids or entity labels (auto-
        resolved). Returns ``(source_id, target_id)``.

        If the source/target are labels and don't yet exist, they are created
        as bare entity nodes.
        """
        if not rel_type:
            raise ValueError("rel_type must be non-empty")
        with self._lock:
            src_id = self._resolve_node_ref(source, create_missing=True)
            tgt_id = self._resolve_node_ref(target, create_missing=True)
            if src_id is None:
                raise ValueError(f"could not resolve source node: {source!r}")
            if tgt_id is None:
                raise ValueError(f"could not resolve target node: {target!r}")

            props = dict(properties or {})
            edge_data = {
                "type": props.pop("edge_type", EDGE_TYPE_RELATIONSHIP),
                "rel_type": str(rel_type),
                "fact": props.pop("fact", ""),
                "summary": props.pop("summary", ""),
                "created_at": _iso(_now()),
            }
            for k, v in props.items():
                if k not in edge_data:
                    edge_data[k] = v

            # DiGraph supports a single edge between two nodes — overwrite/merge
            existing = self._graph.get_edge_data(src_id, tgt_id)
            if existing:
                for k, v in edge_data.items():
                    if k not in existing:
                        existing[k] = v
                # keep the rel_type if user provided a new one
                if rel_type:
                    existing["rel_type"] = rel_type
                self._graph.add_edge(src_id, tgt_id, **existing)
            else:
                self._graph.add_edge(src_id, tgt_id, **edge_data)

            self._mirror_neo4j_upsert_edge(src_id, tgt_id, edge_data)
            logger.debug(
                "KG add_relationship: %s -[%s]-> %s", src_id, rel_type, tgt_id
            )
            return src_id, tgt_id

    def add_observation(
        self,
        text: str,
        timestamp: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Add an observation node — a free-form note with a timestamp."""
        if not text:
            raise ValueError("observation text must be non-empty")
        with self._lock:
            ts = _parse_dt(timestamp) or _now()
            node_id = self._new_id("obs")
            meta = dict(metadata or {})
            data = {
                "type": NODE_TYPE_OBSERVATION,
                "label": meta.pop("label", text[:80]),
                "summary": str(text),
                "text": str(text),
                "created_at": _iso(ts),
                "node_id": node_id,
            }
            for k, v in meta.items():
                if k not in data:
                    data[k] = v
            self._graph.add_node(node_id, **data)
            self._mirror_neo4j_upsert_node(node_id)
            logger.debug("KG add_observation: %s", node_id)
            return node_id

    def add_message(
        self,
        role: str,
        content: str,
        timestamp: Optional[str] = None,
    ) -> str:
        """Add a chat message node (role: 'user' / 'assistant' / 'system' / ...)."""
        if not role:
            raise ValueError("role must be non-empty")
        if not content:
            raise ValueError("content must be non-empty")
        with self._lock:
            ts = _parse_dt(timestamp) or _now()
            node_id = self._new_id("msg")
            data = {
                "type": NODE_TYPE_MESSAGE,
                "label": f"{role}: {content[:60]}",
                "summary": str(content),
                "content": str(content),
                "role": str(role),
                "created_at": _iso(ts),
                "node_id": node_id,
            }
            self._graph.add_node(node_id, **data)
            self._mirror_neo4j_upsert_node(node_id)
            logger.debug("KG add_message: %s (%s)", node_id, role)
            return node_id

    def add_episode(
        self,
        episode_id: Optional[str] = None,
        description: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Add an episode node — a wrapper around a tool/agent run.

        If ``episode_id`` is omitted a new one is generated. If an episode
        with that id already exists, its metadata is merged.
        """
        with self._lock:
            meta = dict(metadata or {})
            eid = episode_id or self._new_id("epi")
            if self._graph.has_node(eid):
                data = self._graph.nodes[eid]
                for k, v in meta.items():
                    if k not in data:
                        data[k] = v
                if description and not data.get("summary"):
                    data["summary"] = description
                return eid
            data = {
                "type": NODE_TYPE_EPISODE,
                "label": meta.pop("label", eid),
                "summary": str(description),
                "created_at": _iso(_now()),
                "node_id": eid,
            }
            for k, v in meta.items():
                if k not in data:
                    data[k] = v
            self._graph.add_node(eid, **data)
            self._mirror_neo4j_upsert_node(eid)
            return eid

    def link_episode(
        self,
        episode_id: str,
        node_id: str,
        rel_type: str = EDGE_TYPE_REFERENCES,
    ) -> None:
        """Link an episode to another node (observation / message / entity)."""
        with self._lock:
            if not self._graph.has_node(episode_id) or not self._graph.has_node(node_id):
                return
            self._graph.add_edge(
                episode_id,
                node_id,
                type=rel_type,
                rel_type=rel_type,
                created_at=_iso(_now()),
            )

    # ── Resolution helpers ────────────────────────────────────────────────

    def _resolve_node_ref(self, ref: str, create_missing: bool = False) -> Optional[str]:
        """Resolve a node reference: by node_id first, then by entity label."""
        if not ref:
            return None
        if self._graph.has_node(ref):
            return ref
        # Try exact entity-label match
        nid = self._find_entity_by_label(ref)
        if nid is not None:
            return nid
        if create_missing:
            # Create a bare entity node so relationships are never lost
            return self.add_entity(ref, entity_type="auto")
        return None

    # ── Neo4j mirroring (best-effort) ───────────────────────────────────────

    def _mirror_neo4j_upsert_node(self, node_id: str) -> None:
        if not self.has_neo4j:
            return
        try:
            data = dict(self._graph.nodes[node_id])
            labels = [data.get("type", "Entity")]
            cypher = (
                "MERGE (n:KGNode {node_id: $node_id}) "
                "SET n += $props SET n:" + ":".join(labels)
            )
            with self._neo4j_driver.session() as sess:  # type: ignore[attr-defined]
                sess.run(cypher, {"node_id": node_id, "props": _jsonable(data)})
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.debug("Neo4j node upsert failed: %s", exc)

    def _mirror_neo4j_upsert_edge(
        self, src: str, tgt: str, edge_data: Dict[str, Any]
    ) -> None:
        if not self.has_neo4j:
            return
        try:
            cypher = (
                "MATCH (a:KGNode {node_id: $src}), (b:KGNode {node_id: $tgt}) "
                "MERGE (a)-[r:KG_REL]->(b) SET r += $props"
            )
            with self._neo4j_driver.session() as sess:  # type: ignore[attr-defined]
                sess.run(
                    cypher,
                    {"src": src, "tgt": tgt, "props": _jsonable(edge_data)},
                )
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.debug("Neo4j edge upsert failed: %s", exc)

    # ── Search methods (the 7 types) ────────────────────────────────────────

    def search_temporal(
        self,
        start: str,
        end: str,
        max_results: int = DEFAULT_TEMPORAL_MAX_RESULTS,
    ) -> list:
        """1. Temporal-window search — all nodes with ``created_at`` in [start, end]."""
        start_dt = _parse_dt(start)
        end_dt = _parse_dt(end)
        if start_dt is None or end_dt is None:
            return [f"[ERROR] Invalid temporal window: start={start!r}, end={end!r}"]
        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt
        max_results = max(1, int(max_results))

        with self._lock:
            matches: List[Tuple[datetime, str]] = []
            for nid, data in self._graph.nodes(data=True):
                dt = _parse_dt(data.get("created_at"))
                if dt is None:
                    continue
                if start_dt <= dt <= end_dt:
                    matches.append((dt, nid))
            matches.sort(key=lambda x: x[0])

        if not matches:
            return [
                f"No nodes found in temporal window [{start} → {end}]. "
                f"Graph has {self._graph.number_of_nodes()} nodes total."
            ]

        lines = [
            f"Temporal window search [{start} → {end}]: "
            f"{len(matches)} match(es), showing top {min(max_results, len(matches))}."
        ]
        for dt, nid in matches[:max_results]:
            lines.append("")
            lines.append(self._format_node(nid))
        return lines

    def search_entity_relationships(
        self,
        center_entity: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_results: int = DEFAULT_RELATIONSHIP_MAX_RESULTS,
    ) -> list:
        """2. Entity-relationship search — BFS from a center entity."""
        if not center_entity:
            return ["[ERROR] center_entity is required"]
        max_depth = max(1, min(int(max_depth), MAX_ALLOWED_DEPTH))
        max_results = max(1, int(max_results))

        with self._lock:
            center_id = self._resolve_node_ref(center_entity, create_missing=False)
            if center_id is None:
                return [
                    f"Entity '{center_entity}' not found in knowledge graph. "
                    f"Use `add_entity` first or check the label."
                ]

            # BFS — collect (node_id, depth)
            visited: Dict[str, int] = {center_id: 0}
            queue: deque = deque([(center_id, 0)])
            edges_seen: List[Tuple[str, str, Dict[str, Any]]] = []

            while queue:
                nid, depth = queue.popleft()
                if depth >= max_depth:
                    continue
                # Outgoing edges
                for _, tgt, edata in self._graph.out_edges(nid, data=True):
                    edges_seen.append((nid, tgt, dict(edata)))
                    if tgt not in visited:
                        visited[tgt] = depth + 1
                        queue.append((tgt, depth + 1))
                # Incoming edges (relationships are bidirectionally interesting)
                for src, _, edata in self._graph.in_edges(nid, data=True):
                    edges_seen.append((src, nid, dict(edata)))
                    if src not in visited:
                        visited[src] = depth + 1
                        queue.append((src, depth + 1))

        if not edges_seen and len(visited) == 1:
            return [
                f"Entity '{center_entity}' exists but has no relationships within "
                f"depth {max_depth}."
            ]

        lines = [
            f"Entity-relationship search for '{center_entity}' "
            f"(depth≤{max_depth}): {len(visited)} node(s), "
            f"{len(edges_seen)} edge(s). Showing top {max_results}."
        ]
        lines.append("")
        lines.append(self._format_node(center_id))
        shown = 0
        for src, tgt, edata in edges_seen:
            if shown >= max_results:
                break
            lines.append(self._format_edge(src, tgt, edata))
            shown += 1
        if len(edges_seen) > max_results:
            lines.append(f"  ... and {len(edges_seen) - max_results} more edge(s).")
        return lines

    def search_diverse(
        self,
        query: str,
        max_results: int = DEFAULT_DIVERSE_MAX_RESULTS,
        diversity: str = DEFAULT_DIVERSITY_LEVEL,
    ) -> list:
        """3. Diverse-results search — MMR-reranked fuzzy retrieval."""
        if not query:
            return ["[ERROR] query is required"]
        if diversity not in ALLOWED_DIVERSITY_LEVELS:
            return [
                f"[ERROR] diversity must be one of {sorted(ALLOWED_DIVERSITY_LEVELS)}, "
                f"got {diversity!r}"
            ]
        max_results = max(1, int(max_results))
        lambda_ = DIVERSITY_LAMBDA[diversity]
        q_tokens = set(_tokenize(query))

        with self._lock:
            scored: List[Tuple[str, float, Dict[str, Any]]] = []
            for nid, data in self._graph.nodes(data=True):
                haystack = " ".join(
                    str(data.get(k, ""))
                    for k in ("label", "summary", "text", "content", "entity_type")
                )
                tokens = _tokenize(haystack)
                if not tokens:
                    continue
                rel = _jaccard_similarity(q_tokens, tokens)
                # Boost: exact substring match on label or summary
                if query.lower() in (data.get("label", "") + " " + data.get("summary", "")).lower():
                    rel = max(rel, 0.6)
                if rel <= 0:
                    continue
                scored.append((nid, rel, dict(data)))
            scored.sort(key=lambda x: x[1], reverse=True)

        if not scored:
            return [
                f"No diverse matches for query '{query}'. "
                f"Graph has {self._graph.number_of_nodes()} nodes total."
            ]

        selected = _mmr_select(scored, max_results, lambda_)
        lines = [
            f"Diverse search '{query}' (diversity={diversity}, λ={lambda_}): "
            f"{len(scored)} candidate(s), top {len(selected)} selected."
        ]
        for data in selected:
            lines.append("")
            nid = data.get("node_id", "?")
            lines.append(self._format_node(nid))
        return lines

    def search_episode_context(
        self,
        episode_id: str,
        max_results: int = DEFAULT_EPISODE_MAX_RESULTS,
    ) -> list:
        """4. Episode-context search — all nodes referenced by an episode."""
        if not episode_id:
            return ["[ERROR] episode_id is required"]
        max_results = max(1, int(max_results))

        with self._lock:
            # Resolve episode id (exact match first, then partial)
            ep_id = episode_id if self._graph.has_node(episode_id) else None
            if ep_id is None:
                # Try substring match on labels/ids of episode nodes
                for nid, data in self._graph.nodes(data=True):
                    if data.get("type") != NODE_TYPE_EPISODE:
                        continue
                    if episode_id in nid or episode_id in str(data.get("label", "")):
                        ep_id = nid
                        break
            if ep_id is None:
                return [
                    f"Episode '{episode_id}' not found. "
                    f"Use `add_episode` to create one."
                ]

            related: List[Tuple[str, Dict[str, Any]]] = []
            # Direct outgoing references
            for _, tgt, edata in self._graph.out_edges(ep_id, data=True):
                related.append((tgt, dict(edata)))
            # Also include nodes that reference this episode
            for src, _, edata in self._graph.in_edges(ep_id, data=True):
                related.append((src, dict(edata)))

        lines = [
            f"Episode-context search '{episode_id}': "
            f"{len(related)} related node(s), showing top {min(max_results, len(related))}."
        ]
        lines.append("")
        lines.append(self._format_node(ep_id))
        shown = 0
        for nid, edata in related[:max_results]:
            lines.append("")
            lines.append(self._format_node(nid))
            etype = edata.get("type", "reference")
            lines.append(f"  (via {etype})")
            shown += 1
        if len(related) > max_results:
            lines.append(f"\n  ... and {len(related) - max_results} more.")
        return lines

    def search_successful_tools(
        self,
        task_type: Optional[str] = None,
        max_results: int = DEFAULT_SUCCESSFUL_MAX_RESULTS,
    ) -> list:
        """5. Successful-tools search — episodes / observations tagged as successful."""
        max_results = max(1, int(max_results))
        task_lower = task_type.lower() if task_type else None

        with self._lock:
            matches: List[Tuple[datetime, str, Dict[str, Any]]] = []
            for nid, data in self._graph.nodes(data=True):
                # Successful tool executions are typically stored as episodes
                # or observations with a ``success=True`` flag.
                success_flag = data.get("success") or data.get("successful") or data.get("status") == "success"
                if not success_flag:
                    continue
                # Optional task_type filter
                if task_lower:
                    tt = str(data.get("task_type") or data.get("tool") or data.get("entity_type") or "").lower()
                    if task_lower not in tt:
                        continue
                dt = _parse_dt(data.get("created_at")) or _now()
                matches.append((dt, nid, dict(data)))
            matches.sort(key=lambda x: x[0], reverse=True)

        if not matches:
            tag = f" for task_type='{task_type}'" if task_type else ""
            return [
                f"No successful tool executions found{tag}. "
                f"Add episodes/observations with success=True to populate this index."
            ]

        lines = [
            f"Successful-tools search{(' task_type=' + repr(task_type)) if task_type else ''}: "
            f"{len(matches)} match(es), showing top {min(max_results, len(matches))}."
        ]
        for _, nid, _ in matches[:max_results]:
            lines.append("")
            lines.append(self._format_node(nid))
        return lines

    def search_recent_context(
        self,
        max_results: int = DEFAULT_RECENT_MAX_RESULTS,
        recency: str = DEFAULT_RECENCY_WINDOW,
    ) -> list:
        """6. Recent-context search — recency-bounded context window."""
        if recency not in ALLOWED_RECENCY_WINDOWS:
            return [
                f"[ERROR] recency must be one of {sorted(ALLOWED_RECENCY_WINDOWS)}, "
                f"got {recency!r}"
            ]
        max_results = max(1, int(max_results))
        delta = RECENCY_WINDOW_DELTA[recency]
        cutoff = _now() - delta

        with self._lock:
            matches: List[Tuple[datetime, str]] = []
            for nid, data in self._graph.nodes(data=True):
                dt = _parse_dt(data.get("created_at"))
                if dt is None:
                    continue
                if dt >= cutoff:
                    matches.append((dt, nid))
            matches.sort(key=lambda x: x[0], reverse=True)

        if not matches:
            return [
                f"No nodes in the last {recency}. "
                f"Graph has {self._graph.number_of_nodes()} nodes total."
            ]

        lines = [
            f"Recent-context search (last {recency}): "
            f"{len(matches)} match(es), showing top {min(max_results, len(matches))}."
        ]
        for _, nid in matches[:max_results]:
            lines.append("")
            lines.append(self._format_node(nid))
        return lines

    def search_entity_by_label(
        self,
        label: str,
        max_results: int = DEFAULT_LABEL_MAX_RESULTS,
    ) -> list:
        """7. Entity-by-label search — substring match on entity labels."""
        if not label:
            return ["[ERROR] label is required"]
        max_results = max(1, int(max_results))
        target = label.strip().lower()

        with self._lock:
            matches: List[Tuple[str, Dict[str, Any]]] = []
            for nid, data in self._graph.nodes(data=True):
                if data.get("type") != NODE_TYPE_ENTITY:
                    continue
                lbl = str(data.get("label", "")).lower()
                if not lbl:
                    continue
                if target in lbl:
                    matches.append((nid, dict(data)))
            # Sort: exact match first, then alphabetical
            matches.sort(key=lambda x: (x[1].get("label", "").lower() != target, x[1].get("label", "")))

        if not matches:
            return [
                f"No entities matching label '{label}'. "
                f"Graph has {self._graph.number_of_nodes()} nodes total."
            ]

        lines = [
            f"Entity-by-label search '{label}': "
            f"{len(matches)} match(es), showing top {min(max_results, len(matches))}."
        ]
        for nid, _ in matches[:max_results]:
            lines.append("")
            lines.append(self._format_node(nid))
        return lines

    # ── Raw accessors (for programmatic use) ────────────────────────────────

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Return a copy of a node's data, or None."""
        with self._lock:
            if not self._graph.has_node(node_id):
                return None
            return dict(self._graph.nodes[node_id])

    def list_nodes(self, node_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all nodes (optionally filtered by ``type``)."""
        with self._lock:
            out = []
            for nid, data in self._graph.nodes(data=True):
                if node_type and data.get("type") != node_type:
                    continue
                row = dict(data)
                row.setdefault("node_id", nid)
                out.append(row)
            return out

    def list_edges(self) -> List[Dict[str, Any]]:
        """Return all edges as dicts with ``source``/``target`` keys."""
        with self._lock:
            out = []
            for u, v, data in self._graph.edges(data=True):
                row = dict(data)
                row["source"] = u
                row["target"] = v
                out.append(row)
            return out

    # ── Persistence ────────────────────────────────────────────────────────

    def save(self, path: Optional[str] = None) -> str:
        """Persist the graph to disk as JSON. Returns the path written."""
        with self._lock:
            target = Path(path).expanduser() if path else self._persistence_path
            if target is None:
                raise ValueError("no persistence path provided")
            target.parent.mkdir(parents=True, exist_ok=True)

            nodes = []
            for nid, data in self._graph.nodes(data=True):
                nodes.append({"id": nid, "data": _jsonable(data)})

            edges = []
            for u, v, data in self._graph.edges(data=True):
                edges.append(
                    {"source": u, "target": v, "data": _jsonable(data)}
                )

            payload = {
                "version": 1,
                "saved_at": _iso(_now()),
                "nodes": nodes,
                "edges": edges,
            }
            target.write_text(json.dumps(payload, indent=2, default=str))
            logger.info("KG saved → %s (%d nodes, %d edges)",
                        target, len(nodes), len(edges))
            return str(target)

    def load(self, path: Optional[str] = None) -> None:
        """Load the graph from a JSON file, replacing the in-memory graph."""
        target = Path(path).expanduser() if path else self._persistence_path
        if target is None or not target.exists():
            raise FileNotFoundError(f"KG file not found: {target}")

        payload = json.loads(target.read_text())
        with self._lock:
            self._graph = self._nx.DiGraph()
            for node in payload.get("nodes", []):
                nid = node["id"]
                data = node.get("data", {})
                self._graph.add_node(nid, **data)
            for edge in payload.get("edges", []):
                u = edge["source"]
                v = edge["target"]
                data = edge.get("data", {})
                if self._graph.has_node(u) and self._graph.has_node(v):
                    self._graph.add_edge(u, v, **data)
        logger.info("KG loaded ← %s (%d nodes, %d edges)",
                    target, self._graph.number_of_nodes(), self._graph.number_of_edges())

    def clear(self) -> None:
        """Wipe the in-memory graph (does NOT delete the persistence file)."""
        with self._lock:
            self._graph = self._nx.DiGraph()
            logger.info("KG cleared")

    def stats(self) -> Dict[str, Any]:
        """Return summary statistics about the graph."""
        with self._lock:
            type_counts: Dict[str, int] = {}
            for _, data in self._graph.nodes(data=True):
                t = data.get("type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1

            rel_counts: Dict[str, int] = {}
            for _, _, data in self._graph.edges(data=True):
                rt = data.get("rel_type") or data.get("type", "unknown")
                rel_counts[rt] = rel_counts.get(rt, 0) + 1

            return {
                "node_count": self._graph.number_of_nodes(),
                "edge_count": self._graph.number_of_edges(),
                "nodes_by_type": type_counts,
                "edges_by_type": rel_counts,
                "has_neo4j": self.has_neo4j,
                "persistence_path": str(self._persistence_path) if self._persistence_path else None,
            }

    # ── Convenience ────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return self._graph.number_of_nodes()

    def __contains__(self, ref: str) -> bool:
        with self._lock:
            return self._graph.has_node(ref) or self._find_entity_by_label(ref) is not None

    def __repr__(self) -> str:
        return (
            f"KnowledgeGraph(nodes={self._graph.number_of_nodes()}, "
            f"edges={self._graph.number_of_edges()}, "
            f"neo4j={'on' if self.has_neo4j else 'off'})"
        )


# ──────────────────────────────────────────────────────────────────────────────
# JSON sanitisation helper (module-level for reuse)
# ──────────────────────────────────────────────────────────────────────────────


def _jsonable(obj: Any) -> Any:
    """Best-effort conversion of arbitrary objects to JSON-safe types."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, datetime):
        return _iso(obj)
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, set):
        return [_jsonable(x) for x in obj]
    # Fall back to string representation
    return str(obj)


__all__ = ["KnowledgeGraph"]
