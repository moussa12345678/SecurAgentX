"""securagentx.knowledge_graph — Knowledge Graph entity extraction & integration.

This subpackage implements the Graphiti-backed knowledge-graph layer for
SecurAgentX. It is composed of six modules:

* ``kg_store``    — :class:`KnowledgeGraph` synchronous networkx-backed store
  with the 7 Graphiti search types and optional Neo4j mirroring.
  (Task IMPL-KG.)
* ``kg_tool``     — :class:`KnowledgeGraphTool` agent-facing wrapper that
  exposes the 7 search actions plus ingestion utilities via a single
  ``handle(action, args)`` dispatcher. (Task IMPL-KG.)
* ``graph``       — async core primitives (:class:`Node`, :class:`Edge`,
  :class:`NodeLabel`, :class:`EdgeType`, :class:`Episode`,
  :class:`Community`, async ``KnowledgeGraph`` — re-exported as
  :class:`AsyncKnowledgeGraph`) backed by NetworkX + SQLite. (Task 5-a.)
* ``extractor``   — :class:`EntityExtractor` regex + LLM extraction of
  entities (IPs, domains, URLs, ports, CVEs, hashes, credentials,
  file paths, service banners, emails) and relationships
  (``HAS_PORT``, ``EXPLOITS``, ``MENTIONS``, ``WORKS_ON``,
  ``DISCOVERED_BY``, ``RELATED_TO``).
* ``integration`` — :class:`KnowledgeGraphIntegration` wires the
  extractor + KnowledgeGraph into VulnAgent's reasoning loop via
  ``on_agent_response`` / ``on_tool_execution`` /
  ``on_finding_discovered`` / ``get_relevant_context`` hooks. All hooks
  are no-ops when the KG is disabled.
* ``community``   — :class:`CommunityDetector` runs NetworkX's Louvain
  (with greedy-modularity fallback) over the per-flow subgraph and
  summarises / merges the resulting communities.

Design constraints
------------------
* The new ``kg_store`` / ``kg_tool`` modules are **synchronous** and depend
  only on ``networkx`` — they are always importable.
* The async modules (``graph`` / ``extractor`` / ``integration`` /
  ``community``) require ``aiosqlite`` and the LLM client SDK. They are
  lazy-imported behind try/except so the package is importable in
  isolation; their symbols are exposed as ``None`` placeholders when their
  dependencies are missing.
* The package-level ``KnowledgeGraph`` symbol refers to the synchronous
  store (Task IMPL-KG). The async version is available as
  :class:`AsyncKnowledgeGraph` and may also be imported directly from
  ``securagentx.knowledge_graph.graph``.
"""

from __future__ import annotations

# ── New synchronous KG (Task IMPL-KG) — always importable ─────────────────
from .kg_store import KnowledgeGraph
from .kg_tool import (
    KnowledgeGraphTool,
    get_default_kg,
    set_default_kg,
)

# ── Async KG modules (Task 5-a) — optional, degrade gracefully ────────────
try:  # pragma: no cover — exercised when aiosqlite is installed
    from .graph import (
        Community,
        Edge,
        EdgeType,
        Episode,
        KnowledgeGraph as AsyncKnowledgeGraph,
        Node,
        NodeLabel,
    )
except Exception:  # noqa: BLE001 — graceful degradation
    # The async graph layer requires aiosqlite; when absent, expose None
    # placeholders so the package is still importable.
    AsyncKnowledgeGraph = None  # type: ignore
    Node = None  # type: ignore
    Edge = None  # type: ignore
    NodeLabel = None  # type: ignore
    EdgeType = None  # type: ignore
    Episode = None  # type: ignore
    Community = None  # type: ignore

try:  # pragma: no cover — exercised when deps are installed
    from .extractor import (
        RELATIONSHIP_EXTRACTION_PROMPT,
        EntityExtractor,
        ExtractedEntity,
    )
except Exception:  # noqa: BLE001 — graceful degradation
    RELATIONSHIP_EXTRACTION_PROMPT = None  # type: ignore
    EntityExtractor = None  # type: ignore
    ExtractedEntity = None  # type: ignore

try:  # pragma: no cover — exercised when deps are installed
    from .integration import (
        KnowledgeGraphIntegration,
        KnowledgeGraphProtocol,
    )
except Exception:  # noqa: BLE001 — graceful degradation
    KnowledgeGraphIntegration = None  # type: ignore
    KnowledgeGraphProtocol = None  # type: ignore

try:  # pragma: no cover — exercised when deps are installed
    from .community import (
        COMMUNITY_SUMMARY_PROMPT,
        DEFAULT_MERGE_THRESHOLD,
        CommunityDetector,
    )
except Exception:  # noqa: BLE001 — graceful degradation
    COMMUNITY_SUMMARY_PROMPT = None  # type: ignore
    DEFAULT_MERGE_THRESHOLD = None  # type: ignore
    CommunityDetector = None  # type: ignore

__all__ = [
    # kg_store (Task IMPL-KG) — primary synchronous KG
    "KnowledgeGraph",
    # kg_tool (Task IMPL-KG)
    "KnowledgeGraphTool",
    "get_default_kg",
    "set_default_kg",
    # graph (Task 5-a) — async, optional
    "AsyncKnowledgeGraph",
    "Node",
    "Edge",
    "NodeLabel",
    "EdgeType",
    "Episode",
    "Community",
    # extractor
    "EntityExtractor",
    "ExtractedEntity",
    "RELATIONSHIP_EXTRACTION_PROMPT",
    # integration
    "KnowledgeGraphIntegration",
    "KnowledgeGraphProtocol",
    # community
    "CommunityDetector",
    "DEFAULT_MERGE_THRESHOLD",
    "COMMUNITY_SUMMARY_PROMPT",
]
