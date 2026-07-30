"""SecurAgentX Knowledge Graph tool — exposes 7 search types to VulnAgent.

This module wraps :class:`securagentx.knowledge_graph.kg_store.KnowledgeGraph`
in a thin dispatcher so VulnAgent can invoke KG queries through a single
``knowledge_graph`` tool entry in ``AVAILABLE_TOOLS``.

Tool actions
------------
The ``handle(action, args)`` method routes to one of:

**Search actions** (return formatted text):
* ``search_temporal``             — args: ``start``, ``end``, ``max_results``
* ``search_entity_relationships`` — args: ``center_entity``, ``max_depth``, ``max_results``
* ``search_diverse``              — args: ``query``, ``max_results``, ``diversity``
* ``search_episode_context``      — args: ``episode_id``, ``max_results``
* ``search_successful_tools``     — args: ``task_type``, ``max_results``
* ``search_recent_context``       — args: ``max_results``, ``recency``
* ``search_entity_by_label``      — args: ``label``, ``max_results``

**Ingestion actions** (return confirmation text):
* ``add_entity``       — args: ``label``, ``entity_type``, ``properties``
* ``add_relationship`` — args: ``source``, ``target``, ``rel_type``, ``properties``
* ``add_observation``  — args: ``text``, ``timestamp``, ``metadata``
* ``add_message``      — args: ``role``, ``content``, ``timestamp``
* ``add_episode``      — args: ``episode_id``, ``description``, ``metadata``

**Utility actions**:
* ``stats``  — return graph statistics
* ``clear``  — wipe the in-memory graph
* ``save``   — persist to disk
* ``load``   — load from disk
* ``help``   — print this list

The tool is *always* available when its :class:`KnowledgeGraph` instance is
constructible (networkx installed). The :meth:`is_available` check returns
``True`` when the underlying KG can be accessed without error.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .kg_store import KnowledgeGraph

logger = logging.getLogger("securagentx.knowledge_graph.kg_tool")

# Module-level singleton — used by VulnAgent's static tool handler when no
# explicit instance is provided. Constructed lazily on first access.
_DEFAULT_KG: Optional[KnowledgeGraph] = None


def get_default_kg() -> KnowledgeGraph:
    """Return (and lazily create) the process-wide default KnowledgeGraph."""
    global _DEFAULT_KG
    if _DEFAULT_KG is None:
        _DEFAULT_KG = KnowledgeGraph()
    return _DEFAULT_KG


def set_default_kg(kg: KnowledgeGraph) -> None:
    """Override the default KG (useful for tests)."""
    global _DEFAULT_KG
    _DEFAULT_KG = kg


class KnowledgeGraphTool:
    """Agent-facing wrapper around :class:`KnowledgeGraph`.

    Examples
    --------
    >>> from securagentx.knowledge_graph.kg_store import KnowledgeGraph
    >>> from securagentx.knowledge_graph.kg_tool import KnowledgeGraphTool
    >>> kg = KnowledgeGraph()
    >>> tool = KnowledgeGraphTool(kg)
    >>> tool.is_available()
    True
    >>> print(tool.handle("add_entity",
    ...                   {"label": "example.com", "entity_type": "domain"})[:80])
    """

    # Action → method name mapping
    SEARCH_ACTIONS: Dict[str, str] = {
        "search_temporal": "search_temporal",
        "temporal_window": "search_temporal",  # alias matching Graphiti name
        "search_entity_relationships": "search_entity_relationships",
        "entity_relationships": "search_entity_relationships",  # alias
        "search_diverse": "search_diverse",
        "diverse_results": "search_diverse",  # alias
        "search_episode_context": "search_episode_context",
        "episode_context": "search_episode_context",  # alias
        "search_successful_tools": "search_successful_tools",
        "successful_tools": "search_successful_tools",  # alias
        "search_recent_context": "search_recent_context",
        "recent_context": "search_recent_context",  # alias
        "search_entity_by_label": "search_entity_by_label",
        "entity_by_label": "search_entity_by_label",  # alias
    }

    INGEST_ACTIONS: Dict[str, str] = {
        "add_entity": "add_entity",
        "add_relationship": "add_relationship",
        "add_observation": "add_observation",
        "add_message": "add_message",
        "add_episode": "add_episode",
    }

    UTILITY_ACTIONS = {"stats", "clear", "save", "load", "help"}

    def __init__(self, kg: Optional[KnowledgeGraph] = None) -> None:
        self._kg: KnowledgeGraph = kg if kg is not None else get_default_kg()

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def kg(self) -> KnowledgeGraph:
        return self._kg

    def is_available(self) -> bool:
        """Return True if the KG can be accessed without error."""
        try:
            # Touch the underlying graph
            _ = self._kg.stats()
            return True
        except Exception as exc:  # noqa: BLE001 — surfaced as 'unavailable'
            logger.warning("KnowledgeGraphTool unavailable: %s", exc)
            return False

    # ── Dispatcher ─────────────────────────────────────────────────────────

    def handle(self, action: str, args: Optional[Dict[str, Any]] = None) -> str:
        """Route ``action`` to the appropriate KG method, return formatted text."""
        args = dict(args or {})
        action = (action or "").strip().lower()

        try:
            if action in self.SEARCH_ACTIONS:
                return self._dispatch_search(action, args)
            if action in self.INGEST_ACTIONS:
                return self._dispatch_ingest(action, args)
            if action in self.UTILITY_ACTIONS:
                return self._dispatch_utility(action, args)
            return self._help_text(
                f"Unknown action: {action!r}. See the help below."
            )
        except Exception as exc:  # noqa: BLE001 — surfaced to agent
            logger.error("KG tool action %s failed: %s", action, exc)
            return f"[ERROR] KG action {action!r} failed: {exc}"

    # ── Search dispatch ────────────────────────────────────────────────────

    def _dispatch_search(self, action: str, args: Dict[str, Any]) -> str:
        method_name = self.SEARCH_ACTIONS[action]
        method: Callable[..., List[str]] = getattr(self._kg, method_name)

        if action in ("search_temporal", "temporal_window"):
            start = args.get("start") or args.get("start_time") or ""
            end = args.get("end") or args.get("end_time") or ""
            max_results = int(args.get("max_results", 15))
            if not start or not end:
                return (
                    "[ERROR] search_temporal requires 'start' and 'end' "
                    "ISO-8601 timestamps."
                )
            results = method(start=start, end=end, max_results=max_results)

        elif action in ("search_entity_relationships", "entity_relationships"):
            center = args.get("center_entity") or args.get("entity") or args.get("label") or ""
            max_depth = int(args.get("max_depth", 2))
            max_results = int(args.get("max_results", 20))
            if not center:
                return "[ERROR] search_entity_relationships requires 'center_entity'."
            results = method(
                center_entity=center,
                max_depth=max_depth,
                max_results=max_results,
            )

        elif action in ("search_diverse", "diverse_results"):
            query = args.get("query") or ""
            max_results = int(args.get("max_results", 10))
            diversity = args.get("diversity", "medium")
            if not query:
                return "[ERROR] search_diverse requires 'query'."
            results = method(
                query=query,
                max_results=max_results,
                diversity=diversity,
            )

        elif action in ("search_episode_context", "episode_context"):
            episode_id = args.get("episode_id") or args.get("episode") or ""
            max_results = int(args.get("max_results", 10))
            if not episode_id:
                return "[ERROR] search_episode_context requires 'episode_id'."
            results = method(episode_id=episode_id, max_results=max_results)

        elif action in ("search_successful_tools", "successful_tools"):
            task_type = args.get("task_type")  # optional
            max_results = int(args.get("max_results", 15))
            results = method(task_type=task_type, max_results=max_results)

        elif action in ("search_recent_context", "recent_context"):
            max_results = int(args.get("max_results", 10))
            recency = args.get("recency", "24h")
            results = method(max_results=max_results, recency=recency)

        elif action in ("search_entity_by_label", "entity_by_label"):
            label = args.get("label") or args.get("entity") or ""
            max_results = int(args.get("max_results", 25))
            if not label:
                return "[ERROR] search_entity_by_label requires 'label'."
            results = method(label=label, max_results=max_results)
        else:  # pragma: no cover — unreachable
            return f"[ERROR] unmapped search action {action!r}"

        return "\n".join(results) if isinstance(results, list) else str(results)

    # ── Ingest dispatch ────────────────────────────────────────────────────

    def _dispatch_ingest(self, action: str, args: Dict[str, Any]) -> str:
        if action == "add_entity":
            label = args.get("label") or ""
            entity_type = args.get("entity_type") or "entity"
            properties = args.get("properties") or {}
            if not label:
                return "[ERROR] add_entity requires 'label'."
            node_id = self._kg.add_entity(
                label=label, entity_type=entity_type, properties=properties
            )
            return f"Entity added: label={label!r} type={entity_type!r} → id={node_id}"

        if action == "add_relationship":
            source = args.get("source") or ""
            target = args.get("target") or ""
            rel_type = args.get("rel_type") or "related_to"
            properties = args.get("properties") or {}
            if not source or not target:
                return "[ERROR] add_relationship requires 'source' and 'target'."
            src_id, tgt_id = self._kg.add_relationship(
                source=source, target=target, rel_type=rel_type, properties=properties
            )
            return (
                f"Relationship added: {src_id} -[{rel_type}]-> {tgt_id}"
            )

        if action == "add_observation":
            text = args.get("text") or ""
            timestamp = args.get("timestamp")
            metadata = args.get("metadata") or {}
            if not text:
                return "[ERROR] add_observation requires 'text'."
            node_id = self._kg.add_observation(
                text=text, timestamp=timestamp, metadata=metadata
            )
            return f"Observation added → id={node_id}"

        if action == "add_message":
            role = args.get("role") or ""
            content = args.get("content") or ""
            timestamp = args.get("timestamp")
            if not role or not content:
                return "[ERROR] add_message requires 'role' and 'content'."
            node_id = self._kg.add_message(
                role=role, content=content, timestamp=timestamp
            )
            return f"Message added (role={role!r}) → id={node_id}"

        if action == "add_episode":
            episode_id = args.get("episode_id")
            description = args.get("description") or ""
            metadata = args.get("metadata") or {}
            eid = self._kg.add_episode(
                episode_id=episode_id, description=description, metadata=metadata
            )
            return f"Episode added → id={eid}"

        return f"[ERROR] unmapped ingest action {action!r}"  # pragma: no cover

    # ── Utility dispatch ───────────────────────────────────────────────────

    def _dispatch_utility(self, action: str, args: Dict[str, Any]) -> str:
        if action == "stats":
            stats = self._kg.stats()
            lines = [
                "Knowledge Graph stats:",
                f"  nodes: {stats['node_count']}",
                f"  edges: {stats['edge_count']}",
                f"  nodes_by_type: {stats['nodes_by_type']}",
                f"  edges_by_type: {stats['edges_by_type']}",
                f"  neo4j_backend: {'on' if stats['has_neo4j'] else 'off'}",
                f"  persistence_path: {stats['persistence_path']}",
            ]
            return "\n".join(lines)

        if action == "clear":
            self._kg.clear()
            return "Knowledge graph cleared (in-memory). Persistence file unchanged."

        if action == "save":
            path = args.get("path")
            written = self._kg.save(path)
            return f"Knowledge graph saved → {written}"

        if action == "load":
            path = args.get("path")
            try:
                self._kg.load(path)
                return f"Knowledge graph loaded (path={path or 'default'})"
            except FileNotFoundError as exc:
                return f"[ERROR] {exc}"

        if action == "help":
            return self._help_text()

        return f"[ERROR] unmapped utility action {action!r}"  # pragma: no cover

    # ── Help text ─────────────────────────────────────────────────────────

    def _help_text(self, prefix: str = "") -> str:
        lines = []
        if prefix:
            lines.append(prefix)
            lines.append("")
        lines.append("KnowledgeGraphTool — available actions:")
        lines.append("")
        lines.append("Search actions (7 types):")
        lines.append("  search_temporal            — args: start, end, max_results")
        lines.append("  search_entity_relationships — args: center_entity, max_depth, max_results")
        lines.append("  search_diverse             — args: query, max_results, diversity")
        lines.append("  search_episode_context     — args: episode_id, max_results")
        lines.append("  search_successful_tools    — args: task_type(optional), max_results")
        lines.append("  search_recent_context      — args: max_results, recency(1h|6h|24h|7d)")
        lines.append("  search_entity_by_label     — args: label, max_results")
        lines.append("")
        lines.append("Ingest actions:")
        lines.append("  add_entity       — args: label, entity_type, properties")
        lines.append("  add_relationship — args: source, target, rel_type, properties")
        lines.append("  add_observation  — args: text, timestamp, metadata")
        lines.append("  add_message      — args: role, content, timestamp")
        lines.append("  add_episode      — args: episode_id(optional), description, metadata")
        lines.append("")
        lines.append("Utility actions:")
        lines.append("  stats            — show graph statistics")
        lines.append("  clear            — wipe in-memory graph")
        lines.append("  save             — persist to disk (args: path optional)")
        lines.append("  load             — load from disk (args: path optional)")
        lines.append("  help             — show this message")
        return "\n".join(lines)


__all__ = ["KnowledgeGraphTool", "get_default_kg", "set_default_kg"]
