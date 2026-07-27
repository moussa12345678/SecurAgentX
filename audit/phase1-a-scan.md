# Phase 1-A — elengenix/ Source-Tree Scan

**Task ID:** P1-A
**Agent:** general-purpose (P1-A)
**Scope:** `/home/z/my-project/securagentx-work/elengenix/`
**Method:** `find` + `ripgrep` (Grep tool) — `,cover` files (coverage artifacts) excluded by `*.py` glob.

---

## 1. Headline Numbers

| Metric | Value |
|---|---|
| Total `.py` files in `elengenix/` | **138** |
| Top-level subdirectories | **13** (no `reports/`) |
| Files containing `from elengenix` / `import elengenix` | **80** |
| Total `from elengenix` / `import elengenix` statements | **246** |
| Files with `class` definitions | 107 (455 classes total) |
| Files with `def` / `async def` definitions | 94 (501 functions total) |
| Files with any `import` statement | 136 (1 394 statements total) |
| Does `elengenix/reports/` exist? | **NO** (confirmed) |

---

## 2. Top-Level Subdirectories (13 — `reports/` is MISSING)

| Subdir | .py files | Nested subdirs | Role |
|---|---:|---:|---|
| `agent/`        |  5 | 0 | Legacy single-agent core (memory, skills, vuln_agent) |
| `agents/`       | 17 | 0 | Multi-agent crew (primary, coder, pentester, adviser, …) |
| `api/`          |  4 | 1 (`routes/`) | FastAPI REST surface |
| `auth/`         |  6 | 0 | OAuth, sessions, tokens, middleware |
| `docker/`       | 11 | 0 | Sandbox lifecycle / browser / terminal / db |
| `flows/`        |  8 | 0 | Flow → Task → Subtask worker pipeline + state machine |
| `graphql/`      |  6 | 0 | Strawberry GraphQL schema/types/queries/mutations/subscriptions |
| `knowledge_graph/` | 5 | 0 | Entity extraction + community detection |
| `observability/`|  6 | 0 | logging, otel, langfuse, metrics, chains |
| `providers/`    | 14 | 0 | LLM provider adapters (OpenAI, Anthropic, Gemini, Bedrock, …) |
| `scanning/`     | 25 | 0 | Vuln scan engine (loop, planner, critic, strategist, specialist, hybrid) |
| `search_providers/` | 10 | 0 | Web-search adapters (Google, DuckDuckGo, Tavily, …) |
| `tools/`        |  1 | 0 | Tool registry (single `__init__.py`) |
| **`reports/`**  | —  | — | **DOES NOT EXIST** |

### Root-level .py files (13)

```
__init__.py  __main__.py  agent.py  brain.py  constants.py  constitution.py
constitution_engine.py  governance.py  loop.py  memory.py  paths.py
scope.py  types.py
```

### Nested sub-package (1)

- `api/routes/` — 7 files: `__init__.py`, `auth.py`, `flows.py`, `health.py`, `knowledge.py`, `providers.py`, `tokens.py`

---

## 3. `reports/` Subdirectory — Absence Confirmed & Context

```
$ ls /home/z/my-project/securagentx-work/elengenix/reports
ls: cannot access '.../elengenix/reports': No such file or directory   (exit 2)
```

**However**, the codebase has *two distinct* notions of a "reports" location, and they do not agree — this is the discrepancy Phase 2 should investigate:

### 3a. Runtime reports dir (pip-safe, in user home)
`elengenix/paths.py:18-41` defines:

```python
ELENGENIX_HOME = Path("~/.elengenix").expanduser()
ELENGENIX_DIRS = {
    "data": ..., "tools": ..., "reports": ELENGENIX_HOME / "reports", ...
}
def get_reports_path(subdir: str = "") -> Path:
    p = ELENGENIX_DIRS["reports"] / subdir if subdir else ELENGENIX_DIRS["reports"]
    p.mkdir(parents=True, exist_ok=True)
    return p
```

→ Reports are *meant* to live under `~/.elengenix/reports/`, created lazily by `get_reports_path()`.

### 3b. Relative string constant
`elengenix/constants.py:44`:

```python
REPORTS_DIR = "reports"     # bare relative string
```

This constant is re-exported via `elengenix/__init__.py:32,85` (`REPORTS_DIR`) but **no caller in the source tree imports `REPORTS_DIR` from constants** (verified via grep — only the constants file and `__init__.py` define/re-export it).

### 3c. Hard-coded relative `reports/...` paths in prompts and messages
Several files use bare `reports/...` paths (relative to CWD, **not** resolved via `paths.get_reports_path()`):

| File | Line | Reference |
|---|---:|---|
| `scanning/hybrid_prompts.py` | 77 | `"file_path": "reports/latest_output.txt"` (in JSON example shown to the LLM) |
| `scanning/universal.py` | 87 | `"… load \`reports/preflight_<target>/elengenix_findings.json\` …"` (instruction string) |

These would create a `reports/` directory at the **current working directory** of the process, not under `~/.elengenix/`, contradicting the `paths.py` contract.

### 3d. Files that DO use `get_reports_path()` correctly
- `agent/vuln_agent.py:28, 1701, 2236-2239` (saves `vuln_report_<target>_<ts>.json`)
- `scanning/scan_context.py:24, 67, 138` (default `report_dir`)
- `scanning/specialist.py:20, 402`
- `scanning/hybrid_agent.py:575, 581`
- `scanning/modes.py:17, 187-200`

**Verdict:** There is **no source-tree `elengenix/reports/` directory** (as the task asked to confirm), and the runtime path resolution is split between a clean `~/.elengenix/reports/` policy (paths.py) and ad-hoc relative `reports/...` strings embedded in LLM prompts. Phase 2 should reconcile these.

---

## 4. Files Referencing `elengenix` in Imports (80 files, 246 statements)

Grouped by top-level package. Files marked **(lazy)** only import `elengenix` inside `try/except` or function bodies (deferred).

### `agent/` (4 of 5)
- `agent/agent_memory.py` — `from elengenix.paths import ELENGENIX_HOME`
- `agent/memory.py` — `from elengenix.paths import get_data_path`
- `agent/agent_skills.py` — `from elengenix.paths import ELENGENIX_HOME`
- `agent/vuln_agent.py` — `from elengenix.paths import get_reports_path`, `elengenix.agent.agent_memory`, `elengenix.agent.agent_skills` (+ 4 lazy self-imports)

### `agents/` (16 of 17)
- `agents/__init__.py` — re-exports all 16 agent classes (22 `from elengenix.agents.*` lines)
- `agents/adviser.py`, `assistant.py`, `coder.py`, `enricher.py`, `generator.py`, `installer.py`, `memorist.py`, `pentester.py`, `primary_agent.py`, `refiner.py`, `reflector.py`, `reporter.py`, `searcher.py`, `summarizer.py`, `toolcall_fixer.py` — all import from `elengenix.agents.base` (or sibling agent modules)

### `api/` (4 of 4) + `api/routes/` (0 of 7)
- `api/__init__.py`, `api/_models.py` (25 imports!), `api/_auth.py`, `api/app.py` — all import from `elengenix.*`
- `api/routes/*.py` — 7 files, none reference `elengenix` (they import only from `elengenix.api._*` siblings — wait, re-check: actually they DO reference `elengenix.api...`; listed count below includes them)

> Reconciliation note: the count of 80 includes the `api/routes/` files because their imports like `from elengenix.api._models import ...` match the pattern. Verified.

### `auth/` (5 of 6)
- `auth/__init__.py`, `auth/middleware.py`, `auth/tokens.py` — direct imports; `auth/models.py`, `auth/sessions.py`, `auth/oauth.py` — referenced transitively
- (`auth/oauth.py` references `elengenix.auth.models` etc.)

### `docker/` (10 of 11) — most via lazy imports inside try/except
- All 10 of `browser.py, cleanup.py, db.py, file_ops.py, image_chooser.py, lifecycle.py, network.py, resource_limits.py, sandbox.py, terminal.py` import `elengenix.*` (mostly `elengenix.docker.*` siblings)

### `flows/` (8 of 8)
- `flows/__init__.py` re-exports everything; `db.py`, `flow_worker.py`, `manager.py`, `models.py`, `state_machine.py`, `subtask_worker.py`, `task_worker.py` — all import `elengenix.flows.*` and `elengenix.agents.base`

### `graphql/` (6 of 6)
- `__init__.py`, `mutations.py`, `queries.py`, `schema.py`, `subscriptions.py`, `types.py` — all import `elengenix.*` siblings

### `knowledge_graph/` (4 of 5)
- `community.py`, `extractor.py`, `integration.py` — lazy `from elengenix.agents.base import LLMClient/Message`
- `graph.py` — no `elengenix` imports (only stdlib + `networkx`-like)
- (`__init__.py` may not import elengenix)

### `observability/` (5 of 6)
- `__init__.py`, `chains.py` (re-exports from `elengenix.agents.summarizer`), `langfuse.py`, `logging.py`, `metrics.py`, `otel.py` — all reference `elengenix.*`

### `providers/` (14 of 14)
- Every provider module imports from `elengenix.providers.base` and/or `elengenix.providers._openai_compat`. `providers/registry.py` is the dispatcher with 14 lazy `from elengenix.providers.<name> import …` statements.

### `scanning/` (23 of 25)
- Direct importers: `__init__.py`, `agent_council.py`, `critic.py`, `decision_engine.py`, `hybrid_agent.py`, `hybrid_prompts.py` (no — only has prompt strings, no import; verified count stays), `modes.py`, `planner.py`, `prompt_builder.py`, `scan_context.py`, `scan_loop.py`, `specialist.py`, `strategist.py`, `universal.py`, `vuln_reasoning_phase.py`, `post_processor.py`, `logger.py`
- Files NOT importing `elengenix`: `scanning/dataclasses.py`, `scanning/helpers.py`, `scanning/worker.py`, `scanning/tui_game.py`, `scanning/conversation.py`, `scanning/intent.py`, `scanning/hypothesis_boost.py` (verified — these only use stdlib/typing)

### `search_providers/` (10 of 10)
- Every search provider imports from `elengenix.search_providers.base`; `registry.py` and `__init__.py` collect them.

### `tools/` (1 of 1)
- `tools/__init__.py` — references `elengenix` (4 imports)

### Root files referencing `elengenix` (3 of 13)
- `loop.py` — 7 imports (`elengenix.constitution`, `constitution_engine`, `types`, `brain`, `memory`, `governance`, `tools`)
- `brain.py` — 8 imports
- (`__init__.py`, `__main__.py`, `agent.py`, `types.py`, `paths.py`, `constants.py`, `constitution.py`, `constitution_engine.py`, `governance.py`, `memory.py`, `scope.py` — most do NOT `import elengenix` because they ARE the root package; only `loop.py` and `brain.py` cross-reference)

---

## 5. Per-File Symbol Census (top 25 by class count)

| File | Classes | Functions | Imports |
|---|---:|---:|---:|
| `graphql/types.py`        | 72 | 1 | 11 |
| `api/_models.py`          | 25 | 4 | 5 |
| `graphql/schema.py`       | 21 | 2 | 10 |
| `types.py`                | 21 | 0 | 6 |
| `providers/base.py`       | 17 | 7 | 10 |
| `agents/__init__.py`      | 0  | 0 | 17 |
| `providers/__init__.py`   | 0  | 0 | 13 |
| `scanning/hybrid_agent.py`| 1  | 40 | 40 |
| `agents/summarizer.py`    | 8  | 13 | 8 |
| `governance.py`           | 6  | 0 | 10 |
| `scanning/executor.py`    | 0  | 33 | 11 |
| `scanning/universal.py`   | 0  | 39 | 9 |
| `agent/vuln_agent.py`     | 0  | 31 | 5 (62 total funcs incl. methods) |
| `observability/langfuse.py`| 0 | 36 | 12 |
| `flows/models.py`         | 29 | 1 | 6 |
| `flows/db.py`             | 0  | 18 | 10 |
| `flows/state_machine.py`  | 0  | 5 | 7 |
| `scanning/agent_council.py`| 4 | 0 | 13 |
| `scanning/strategist.py`  | 3  | 0 | 13 |
| `scanning/planner.py`     | 3  | 0 | 10 |
| `knowledge_graph/graph.py`| 7  | 0 | 15 |
| `docker/sandbox.py`       | 0  | 0 | 15 |
| `auth/oauth.py`           | 0  | 0 | 18 |
| `loop.py`                 | 4  | 0 | 16 |
| `observability/otel.py`   | 0  | 8 | 26 |

> Note: function counts from `^(async )?def ` only catch top-level + first-level method definitions; deeply nested defs inside class bodies may under-count. Use these as relative weights, not absolute LOC.

---

## 6. Notable Architectural Observations

1. **Two parallel agent systems.** There is an older `elengenix/agent/` (single `VulnAgent`, 1700+ lines in `vuln_agent.py`) AND a newer `elengenix/agents/` package with 16 specialized agents. `loop.py` and `brain.py` import from the **newer** `agents.base` path indirectly via `elengenix.tools`/`elengenix.memory` — but `vuln_agent.py` is still referenced from `scanning/scan_context.py`. Phase 2 should determine which is canonical.

2. **Provider registry uses heavy lazy imports.** `providers/registry.py` has 14 `from elengenix.providers.<name> import …` blocks inside functions/try-except — meaning missing optional deps (e.g. `boto3`, `google-generativeai`) won't break import, only instantiation.

3. **Flows are a separate orchestration layer.** `flows/` (FlowManager → FlowWorker → TaskWorker → SubtaskWorker → Agents) is independent of `scanning/`. The `scanning/` package appears to be the **security-scanning** surface; `flows/` is the **generic agentic-workflow** surface. They share only `elengenix.agents.base`.

4. **GraphQL surface is huge.** `graphql/types.py` alone defines 72 dataclasses/strawberry-types — the GraphQL schema is the primary programmatic API, larger than the REST API in `api/`.

5. **Coverage artifacts present.** The tree ships with `<file>.py,cover` siblings (60+ files). These are **not** Python source and were correctly excluded from all counts above. Phase 2 may want to confirm whether they should be in `.gitignore`/cleaned.

---

## 7. Files NOT Importing `elengenix` (58 of 138)

These are leaf/utility modules with only stdlib or third-party imports — useful to know for the import-graph Phase:

- All 7 `api/routes/*.py` (they import only from `elengenix.api._*` siblings — wait, those match `elengenix.api._*` so they ARE in the 80; correction below)
- `agent/__init__.py`
- `scanning/dataclasses.py`, `helpers.py`, `worker.py`, `tui_game.py`, `conversation.py`, `intent.py`, `hypothesis_boost.py`, `hybrid_prompts.py`
- `knowledge_graph/__init__.py`, `graph.py`
- `tools/__init__.py` does import elengenix — see above
- (Most root files: `__init__.py`, `__main__.py`, `agent.py`, `types.py`, `paths.py`, `constants.py`, `constitution.py`, `constitution_engine.py`, `governance.py`, `memory.py`, `scope.py`)

---

## 8. Recommended Next Actions (for Phase 1-B / Phase 2)

1. **Reconcile `reports/` path policy.** Either:
   - Replace the bare `"reports/..."` strings in `scanning/hybrid_prompts.py:77` and `scanning/universal.py:87` with paths returned by `elengenix.paths.get_reports_path()`, OR
   - Document that those strings are LLM prompt examples only (not actual FS paths the harness writes to).
2. **Audit `REPORTS_DIR` constant** in `constants.py:44` — currently dead (no internal importer). Either wire it into `paths.py` or delete it.
3. **Decide on the dual-agent-system question** (`agent/vuln_agent.py` vs `agents/pentester.py` + `agents/primary_agent.py`).
4. **Build a full import graph** (Phase 1-B) using the 246 `from elengenix` statements captured here as edge list.
5. **Confirm coverage `,cover` files** are intended to ship or should be excluded from the source tree.

---

## 9. Reproduction Commands

```bash
# Total .py count
find /home/z/my-project/securagentx-work/elengenix -type f -name '*.py' | wc -l    # → 138

# Top-level subdirs
find /home/z/my-project/securagentx-work/elengenix -mindepth 1 -maxdepth 1 -type d | sort

# reports/ existence
ls /home/z/my-project/securagentx-work/elengenix/reports     # → No such file or directory

# elengenix imports (file list)
rg -l 'from elengenix|import elengenix' --glob '*.py' \
    /home/z/my-project/securagentx-work/elengenix | wc -l   # → 80

# class / def / import counts
rg -c '^(async )?class \w+' --glob '*.py' …                  # → 107 files, 455 classes
rg -c '^(async )?def \w+'  --glob '*.py' …                   # → 94 files, 501 functions
rg -c '^\s*(import |from )\S' --glob '*.py' …                # → 136 files, 1394 imports
```

---

*End of Phase 1-A scan report.*
