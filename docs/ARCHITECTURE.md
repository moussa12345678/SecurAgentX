# SecurAgentX — Dual-Tree Architecture (P1.6 Documentation)

> **Status:** Documentation of the *current* (post-migration) dual-tree state.
> **Audience:** Contributors, reviewers, and the next agent tasked with
> collapsing the duplication.
> **Related task:** P1.6 — "Document dual-tree split-brain".

---

## 1. TL;DR

The repository ships **two parallel source trees** under the same installable
package:

| Tree                  | Role                  | Status                              |
|-----------------------|-----------------------|-------------------------------------|
| `securagentx/`        | **Canonical** tree    | Active development target           |
| `core/`, `agents/`, `tools/`, `tui/`, `cli/`, `commands/` | **Legacy** tree | Half-shimmed, half-live |

**The legacy tree is NOT a pure shim layer.** Only the `__init__.py` files
of `core/` and `agents/` actually behave as proper shims (re-export +
`DeprecationWarning`). The remaining files are **full implementations that
are still on the production import path** — they are *not* safe to delete.

**VERDICT (P1.6):** This is a **split-brain** state. Documentation only —
no code deletion is performed in this task. See §7 for the recommended
collapse path.

---

## 2. What "canonical" means here

`securagentx/` is the long-term home for the framework. It contains the
next-generation cognitive architecture:

- `securagentx/brain.py`        — `TrueAIBrain` (cognitive core)
- `securagentx/loop.py`         — `TrueAgenticLoop` (autonomous loop)
- `securagentx/constitution_engine.py`, `securagentx/constitution.py`
- `securagentx/governance.py`   — `GovernanceGate`
- `securagentx/memory.py`       — `CognitiveMemoryManager`
- `securagentx/providers/`      — LLM provider registry (OpenAI, Anthropic, Gemini, Qwen, GLM, Bedrock, Ollama, Kimi, DeepSeek, custom…)
- `securagentx/scanning/`       — Refactored scan-loop stack (`ScanLoop`, `DecisionEngine`, `PromptBuilder`, `ScanContext`, `PostExecutionProcessor`, planner, executor, council, critic, specialist, strategist, hybrid_agent, universal, …)
- `securagentx/tools/`          — `ToolRegistry`, `ToolMetadata`, `ToolResult` (the canonical tool protocol)
- `securagentx/agents/`         — Role-based agents (adviser, coder, enricher, memorist, pentester, primary_agent, refiner, reflector, reporter, searcher, summarizer, installer, toolcall_fixer, generator)
- `securagentx/auth/`, `securagentx/api/`, `securagentx/graphql/` — FastAPI + Strawberry GraphQL surface
- `securagentx/docker/`, `securagentx/flows/`, `securagentx/knowledge_graph/`, `securagentx/observability/`, `securagentx/reports/`, `securagentx/search_providers/`

**New code MUST import from `securagentx.*`.** No new modules should be
added under `core/`, `agents/`, `tools/`, `tui/`, `cli/`, or `commands/`.

---

## 3. The legacy tree — file-by-file reality check

The following table is the actual on-disk state (audited 2026-07-28 via
`wc -l` + `diff` against `securagentx/` counterparts).

### 3.1 `core/` — 1,299 lines across 5 files

| File                     | Lines | True shim? | Notes |
|--------------------------|------:|:----------:|-------|
| `core/__init__.py`       |  15   | **YES**    | Emits `DeprecationWarning`; no re-export. |
| `core/agent.py`          |  28   | partial    | Just `from core.brain import SecurAgentXAgent` — a re-export shim, but no DeprecationWarning. |
| `core/brain.py`          | **1,089** | **NO**  | Full `SecurAgentXAgent` implementation (different class from `securagentx.brain.TrueAIBrain`). Still imported by `main.py`? **No — but** imported by `tools/overlay_menu.py`, `integrations/bot.py`, `core/agent.py`, and `tests/test_brain_coverage_gap.py` (747 lines of coverage tests written against THIS implementation). |
| `core/orchestrator.py`   |  145  | **NO**     | `is_in_scope`, `normalize_target`, `run_standard_scan`. Imported by `main.py` (lines 194, 205) and `tools/omni_scan.py`. **On the production path.** |
| `core/scan_engine.py`    |  22   | partial    | Tiny wrapper; not yet audited for callers. |

### 3.2 `agents/` — ~9,400 lines across 22 files

| File                         | Lines | True shim? | Notes |
|------------------------------|------:|:----------:|-------|
| `agents/__init__.py`         |  35   | **YES**    | Re-exports `ScanLoop`, `DecisionEngine`, `PostExecutionProcessor`, `PromptBuilder`, `ScanContext`, `ScanResult` from `securagentx.scanning.*` and emits `DeprecationWarning`. **The only file in `agents/` that is a real shim.** |
| `agents/scan_loop.py`        |  366  | **NO**     | Diverged from `securagentx/scanning/scan_loop.py` — `diff` = 268 lines. |
| `agents/decision_engine.py`  |  451  | **NO**     | Diverged — `diff` = 333 lines. |
| `agents/scan_context.py`     |  208  | **NO**     | Near-identical to canonical (only docstring + import-path edits — `diff` = 11 lines). |
| `agents/post_processor.py`   |  561  | **NO**     | `diff` = 61 lines. |
| `agents/prompt_builder.py`   |  593  | **NO**     | Near-identical (only import-path edits — `diff` = 4 lines). |
| `agents/agent_*.py` (16 more)| ~6,800| **NO**     | Full agent implementations (council, executor, planner, universal, hybrid, modes, intent, conversation, helpers, logger, dataclasses, vuln_reasoning_phase, tui_game, critic_agent, strategist_agent, specialist_agent, worker_base). The canonical `securagentx/scanning/` versions of these were copied from here and re-import-paths-edited; they have **drifted** since. |

> ⚠️ The `agents/__init__.py` shim re-exports the **canonical** classes — but
> the underlying `agents/scan_loop.py` etc. still contain the **legacy**
> implementations. Anyone doing `from agents.scan_loop import ScanLoop`
> (instead of `from agents import ScanLoop`) silently gets the **wrong**,
> diverged copy. This is the core split-brain hazard.

### 3.3 `tools/` — ~93,000 lines across ~150 files

| File                | Lines | True shim? | Notes |
|---------------------|------:|:----------:|-------|
| `tools/__init__.py` | 1     | **NO**     | Just a docstring: `"""tools package - security tool modules."""`. No `DeprecationWarning`, no re-export. |
| `tools/*.py`        | ~93k  | **NO**     | All full implementations (tool_registry, cvss_calculator, mission_state, universal_ai_client, universal_executor, vuln_engine, vuln_finder, vuln_reasoning, autonomous_agent, zero_day_heuristics, …). This is the **production tool surface** that both `main.py` and `securagentx/scanning/*.py` import from. |

`tools/` is NOT a shim. It is the **active tool layer** that both trees
depend on. The "canonical" `securagentx/tools/__init__.py` only defines the
new `ToolRegistry` protocol — it does NOT contain re-implementations of the
~150 tools under root `tools/`. Until those tools are migrated, the legacy
`tools/` package is **load-bearing**.

### 3.4 `tui/` — ~5,500 lines across 10 files

`tui/__init__.py` is a one-line docstring. All 10 modules (dashboard, export,
findings_display, hunt_view, keyboard_shortcuts, main_menu, scan_progress,
themes, visualizations, welcome) are full implementations imported by
`main.py` (`from tui.main_menu import run_main_menu`). No canonical
counterpart exists in `securagentx/` yet.

### 3.5 `cli/` — ~7,000 lines across 8 files

`cli/__init__.py` is empty. All modules (interactive, live_display, textual,
tools_menu, tui_design, ui_components, wizard) are full implementations
imported by `main.py` and by `tools/*` and `agents/*`. No canonical
counterpart exists in `securagentx/` yet.

### 3.6 `commands/` — ~770 lines across 6 files

`commands/__init__.py` re-exports `CommandRegistry` from its own internal
`commands.registry` module — **NOT** from `securagentx.*`, and **no**
`DeprecationWarning`. This is the live command dispatch system, imported by
`main.py` (`from commands.mcp_runner import start_mcp_if_enabled`,
`from commands.scan import handle_scan`).

---

## 4. Where the dual-tree actually touches at runtime

### 4.1 Cross-imports from `securagentx/` into the legacy tree

`securagentx/scanning/` is **not** self-contained — it depends on the legacy
`tools/` and `cli/` packages:

```
securagentx/scanning/hybrid_agent.py   → 10 imports from tools.* + cli.ui_components
securagentx/scanning/agent_council.py  → 1 import  from tools.*
securagentx/scanning/universal.py      → 7 imports from tools.* + securagentx.brain
securagentx/scanning/executor.py       → 4 imports from tools.*
securagentx/scanning/planner.py        → 3 imports from tools.*
securagentx/scanning/modes.py          → 4 imports from tools.*
securagentx/scanning/dataclasses.py    → 1 import  from tools.*
securagentx/scanning/helpers.py        → 1 import  from tools.*
securagentx/scanning/conversation.py   → 1 import  from tools.*
securagentx/scanning/critic.py         → 1 import  from tools.*
securagentx/scanning/strategist.py     → 1 import  from tools.*
securagentx/scanning/specialist.py     → 1 import  from tools.*
securagentx/scanning/intent.py         → 1 import  from tools.*
```

Total: **13 canonical modules depend on the legacy `tools/` / `cli/` packages.**

> **Conclusion:** The legacy `tools/` and `cli/` trees are **load-bearing**
> for the canonical `securagentx/scanning/` stack. They cannot be deleted
> until either (a) the canonical stack is rewritten to use
> `securagentx.tools.*`, or (b) the legacy `tools/` and `cli/` packages are
> moved wholesale into `securagentx/legacy/` and re-exported from there.

### 4.2 `main.py` (the package entry point, `[project.scripts] securagentx = "main:main"`)

`main.py` imports:
- `securagentx.paths` — canonical ✅
- `cli.ui_components` — legacy ❌ (production path)
- `core.orchestrator` — legacy ❌ (production path)
- `commands.mcp_runner`, `commands.scan` — legacy ❌ (production path)
- `tools.welcome_wizard`, `tools.history_manager`, `tools.auto_detector`,
  `tools.command_suggest`, `tools.doctor`, `tools.config_wizard`,
  `tools.vuln_researcher`, `tools.autonomous_agent` — legacy ❌ (production path)
- `tui.main_menu` — legacy ❌ (production path)
- `cli.textual`, `cli.interactive` — legacy ❌ (production path)

The CLI entry point is **almost entirely wired to the legacy tree**. The
canonical `securagentx/` tree is reached only via `securagentx.paths`.

### 4.3 Tests

- `tests/test_brain_coverage_gap.py` (747 lines) imports the **legacy**
  `core.brain.SecurAgentXAgent` and exercises its private helpers
  (`_get_db_path`, `_analyze_intent`, `_extract_target_from_text`, …).
- `tests/test_brain.py` imports the **canonical**
  `securagentx.brain.TrueAIBrain` (different class entirely).
- Both test files coexist; both implementations must keep working.

### 4.4 `pyproject.toml` packaging config

```toml
[tool.setuptools.packages.find]
exclude = ["tests*", "venv*", "scripts*", "data*", "reports*", "examples*",
           "htmlcov*", "docs*", ".config*", ".cache*", "build*", "dist*",
           ".mimocode*", ".remember*"]
```

The exclusion list **does NOT exclude `core`, `agents`, `tools`, `tui`,
`cli`, or `commands`**. setuptools auto-discovery therefore installs all
six legacy packages as top-level Python packages alongside `securagentx`.

`securagentx.egg-info/top_level.txt` confirms this — it lists:

```
agents
cli
commands
core
securagentx
tools
tui
… (and several non-Python dirs)
```

So the **published wheel ships both trees** as independently importable
top-level packages. There is no install-time enforcement of the
"deprecated" status.

### 4.5 `[tool.isort] known_first_party`

```toml
known_first_party = ["tools", "agents", "tui", "commands"]
```

isort is told the first-party packages are the **legacy** names —
`securagentx` is not listed. This silently reinforces the legacy tree as
the "real" one for import-sorting purposes.

### 4.6 pytest `filterwarnings`

`pyproject.toml` now reads:

```toml
filterwarnings = [
    "default::DeprecationWarning",
    "default::PendingDeprecationWarning",
    "default::ResourceWarning",
    …
]
```

(The earlier blanket `ignore::DeprecationWarning` was removed — see P4-B in
the worklog.) This means the `core/__init__.py` and `agents/__init__.py`
DeprecationWarnings **will** now surface in test runs, which is the desired
behaviour for tracking the migration.

---

## 5. Risk inventory

| # | Risk | Triggered by | Severity |
|---|------|--------------|----------|
| R1 | **Diverged implementations** — `agents/scan_loop.py` differs from `securagentx/scanning/scan_loop.py` by 268 lines; `agents/decision_engine.py` by 333 lines. | Any code that imports the submodules directly (`from agents.scan_loop import ScanLoop`) instead of via the package (`from agents import ScanLoop`) gets the wrong class. | **High** |
| R2 | **Silent fallback to legacy tree** — `tools/`, `cli/`, `tui/`, `commands/` have no `DeprecationWarning` at all. | New contributors will keep adding code to these directories because nothing tells them not to. | **High** |
| R3 | **`core/__init__.py` warns but does not re-export** — unlike `agents/__init__.py`, it does not redirect imports to `securagentx.*`. | `from core.brain import SecurAgentXAgent` continues to work silently (no warning, since the warning is on `core/__init__.py`, not on `core.brain`). | Medium |
| R4 | **Wheel ships both trees** — `pyproject.toml` `[tool.setuptools.packages.find]` does not exclude the legacy packages. | End-users get a confusing `import core`, `import agents`, `import tools`, `import tui`, `import cli`, `import commands` alongside `import securagentx`, all from the same wheel. | Medium |
| R5 | **isort `known_first_party` is legacy-only** — `securagentx` is absent from the list. | Import sort ordering will be subtly wrong for the canonical tree; linting friction. | Low |
| R6 | **Two `brain.py` classes** — `core.brain.SecurAgentXAgent` (~41 KB) and `securagentx.brain.TrueAIBrain` (~30 KB) are completely different classes with different APIs. | Reviewers / agents reading "brain" must check which one is meant. | Medium |
| R7 | **Coverage tests pin the legacy implementation** — `tests/test_brain_coverage_gap.py` is 747 lines written against `core.brain`. | Deleting `core/brain.py` would delete the test coverage it provides; refactoring would require rewriting those tests. | Medium (migration blocker) |

---

## 6. What "shim" means (terminology)

For the purposes of this document:

- A **true shim** is a module whose *only* runtime behaviour is to re-export
  names from the canonical location and optionally emit a
  `DeprecationWarning`. It contains **no business logic**. The whole module
  should be ~1–30 lines and end with `__all__ = [...]`.
- A **legacy implementation** is a module that contains real business logic,
  regardless of whether its `__init__.py` neighbour happens to warn.

By this definition:
- `core/__init__.py` ✅ true shim (warns; no re-export — partial shim).
- `agents/__init__.py` ✅ true shim (warns + re-exports from `securagentx.scanning`).
- `tools/__init__.py`, `tui/__init__.py`, `cli/__init__.py`, `commands/__init__.py` ❌ not shims — just package markers with no deprecation signal.
- `core/brain.py`, `core/orchestrator.py`, `agents/scan_loop.py`, `agents/decision_engine.py`, every `tools/*.py`, every `tui/*.py`, every `cli/*.py`, every `commands/*.py` ❌ legacy implementations.

---

## 7. Recommended collapse path (follow-up work, not in scope for P1.6)

1. **Decide per-package fate.** For each legacy directory, choose one of:
   - **Migrate** (rewrite against canonical API, delete legacy).
   - **Relocate** (move the legacy directory under `securagentx/legacy/`
     and add a thin top-level re-export shim with `DeprecationWarning`).
   - **Keep** (e.g. for `tools/` if it is agreed to remain the tool layer;
     then update this doc and `securagentx/tools/__init__.py` to reflect
     that `securagentx.tools` is the *protocol* and `tools.*` is the
     *implementation library*).
2. **Reconcile `core/brain.py` vs `securagentx/brain.py`.** Either delete
   `core/brain.py` and migrate `tests/test_brain_coverage_gap.py` to
   `securagentx.brain.TrueAIBrain`, or formally rename `core/brain.py` to
   `securagentx/legacy/brain_v1.py` and make `core/brain.py` a true shim.
3. **Reconcile `agents/scan_loop.py` vs `securagentx/scanning/scan_loop.py`**
   (and the four other diverged siblings). Pick the canonical version, port
   any unique fixes from the other, delete the loser.
4. **Add real `DeprecationWarning`s** to `tools/__init__.py`,
   `tui/__init__.py`, `cli/__init__.py`, `commands/__init__.py` IF those
   directories are destined for migration. If they are destined to stay
   (per step 1), update this document to remove the "deprecated" framing
   for them.
5. **Update `pyproject.toml`:**
   - Add `core*`, `agents*`, `tools*`, `tui*`, `cli*`, `commands*` to the
     `exclude` list of `[tool.setuptools.packages.find]` *only after* the
     shims are confirmed working.
   - Add `securagentx` to `[tool.isort] known_first_party`.
6. **Add CI guard** that fails if any new `from core.|from agents.|from tools.|from tui.|from cli.|from commands.` import appears outside the legacy directories themselves and `tests/`.

---

## 8. Import policy (binding for new code)

| Want | Use | Don't use |
|------|-----|-----------|
| Scan loop | `from securagentx.scanning.scan_loop import ScanLoop` | `from agents.scan_loop import ScanLoop` ❌ |
| Decision engine | `from securagentx.scanning.decision_engine import DecisionEngine` | `from agents.decision_engine import DecisionEngine` ❌ |
| Cognitive brain | `from securagentx.brain import TrueAIBrain` | `from core.brain import SecurAgentXAgent` ❌ (legacy class, different API) |
| Agentic loop | `from securagentx.loop import TrueAgenticLoop` | — |
| Tool registry protocol | `from securagentx.tools import ToolRegistry, ToolResult, ToolMetadata` | — |
| Concrete tool implementations | `from tools.<name> import <Class>` (still the only option — see §3.3) | — |
| CLI / TUI helpers | `from cli.ui_components import console, print_error, …` (still the only option — see §3.5) | — |
| Paths / config home | `from securagentx.paths import SECURAGENTX_HOME, get_data_dir` | — |
| LLM providers | `from securagentx.providers import …` | — |

> **Rule of thumb:** if a `securagentx.*` equivalent exists, use it. If it
> does not exist yet (true today for `tools/*`, `cli/*`, `tui/*`,
> `commands/*`), the legacy import is unavoidable — but **do not add new
> modules** to those legacy directories; add them under `securagentx/`
> instead and re-export if backward compatibility is required.

---

## 9. Audit artifacts

- This document: `docs/ARCHITECTURE.md`.
- Per-package line counts and `diff` sizes: captured in §3.
- Cross-import map (`securagentx/* → legacy`): captured in §4.1.
- `securagentx.egg-info/top_level.txt`: confirms both trees ship in the
  wheel (§4.4).

---

**End of P1.6 documentation.**
