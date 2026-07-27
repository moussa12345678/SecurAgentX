# Phase 1-B — Test Directory Map (`tests/`)

**Task ID:** P1-B
**Scope:** Complete map of `/home/z/my-project/securagentx-work/tests/`
**Method:** `find ... -name '*.py'` + `rg` (ripgrep) for imports, `def test_`, `async def test_`, and `elengenix` references.

---

## 1. Headline Metrics

| Metric | Value |
|---|---|
| Total `.py` files in `tests/` (recursive) | **55** |
| Total test functions (`def test_*` + `async def test_*`) | **3,042** |
| └─ sync `def test_*` | 2,627 |
| └─ `async def test_*` | 415 (all in `brutal/`) |
| `.py` files importing directly from `elengenix` | **35** |
| `conftest.py` files | **2** |
| Brutal test files (`tests/brutal/test_*.py`) | **5** (7 total `.py` incl. `conftest.py` + `__init__.py`) |
| Files in `tests/vulnerable_target/` | **1** (`app.py`) |

**Non-test `.py` support files (5, no `def test_*`):**
- `tests/conftest.py`
- `tests/_pkg_helper.py`
- `tests/brutal/conftest.py`
- `tests/brutal/__init__.py` (empty package marker)
- `tests/vulnerable_target/app.py` (deliberately vulnerable Flask target — not a test)

**Other non-`.py` entries in `tests/` (excluded from scan):**
- `tests/API_REFERENCE.md` (doc)
- `tests/ssa` (empty 0-byte file, no extension)

---

## 2. Directory Structure

```
tests/
├── conftest.py                          (sys.path bootstrap, no fixtures)
├── _pkg_helper.py                       (dynamic package-name resolver: 'elen'* dir)
├── API_REFERENCE.md                     (doc, not .py)
├── ssa                                  (empty 0-byte file)
├── test_*.py                            (45 test files)
│
├── brutal/
│   ├── __init__.py                      (empty)
│   ├── conftest.py                      (sys.path bootstrap, no fixtures)
│   └── test_*_brutal.py                 (5 brutal integration test files)
│
└── vulnerable_target/
    └── app.py                           (1 file — deliberately vulnerable Flask app)
```

---

## 3. `conftest.py` Analysis

Both `conftest.py` files contain **only `sys.path` bootstrap logic — zero pytest fixtures defined.**

### `tests/conftest.py` (8 lines)
```python
import os, sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
```

### `tests/brutal/conftest.py` (13 lines)
Mirror of root conftest; inserts `tests/..` (project root) onto `sys.path` so `import elengenix` resolves when pytest is invoked from a sub-directory. **No `@pytest.fixture` decorators, no fixture functions.**

**Implication:** All test setup is done inline (per-test or via module-level helpers), or via `_pkg_helper.py`. No shared fixture layer exists.

---

## 4. Test Function Counts by File

### 4a. Root `tests/test_*.py` (45 files, 1,636 test functions, all sync)

| File | `def test_*` | async | Total |
|---|---:|---:|---:|
| test_scanning_executor.py | 124 | 0 | 124 |
| test_scanning_planner.py | 100 | 0 | 100 |
| test_scanning_post_processor.py | 83 | 0 | 83 |
| test_scanning_decision_engine.py | 77 | 0 | 77 |
| test_brain_coverage_gap.py | 64 | 0 | 64 |
| test_elengix_agent_memory.py | 59 | 0 | 59 |
| test_scanning_helpers.py | 59 | 0 | 59 |
| test_vuln_agent.py | 54 | 0 | 54 |
| test_brain_coverage.py | 50 | 0 | 50 |
| test_scanning_scan_context.py | 45 | 0 | 45 |
| test_scanning_specialist.py | 40 | 0 | 40 |
| test_agent_tools.py | 36 | 0 | 36 |
| test_brain.py | 32 | 0 | 32 |
| test_scanning_agent_council.py | 31 | 0 | 31 |
| test_scanning_universal.py | 31 | 0 | 31 |
| test_scanning_strategist.py | 28 | 0 | 28 |
| test_scanning_vuln_reasoning_phase.py | 27 | 0 | 27 |
| test_scanning_intent.py | 28 | 0 | 28 |
| test_scanning_tui_game.py | 27 | 0 | 27 |
| test_scanning_critic.py | 27 | 0 | 27 |
| test_scanning_conversation.py | 26 | 0 | 26 |
| test_scanning_scan_loop.py | 25 | 0 | 25 |
| test_elengix_scope.py | 24 | 0 | 24 |
| test_constitution_engine.py | 23 | 0 | 23 |
| test_agent_agent_skills.py | 23 | 0 | 23 |
| test_scanning_modes.py | 14 | 0 | 14 |
| test_mcp_config.py | 14 | 0 | 14 |
| test_mcp_client.py | 13 | 0 | 13 |
| test_loop.py | 13 | 0 | 13 |
| test_scanning_hypothesis_boost.py | 13 | 0 | 13 |
| test_elengix_governance.py | 12 | 0 | 12 |
| test_elengix_paths.py | 18 | 0 | 18 |
| test_tools_tool_recommender.py | 14 | 0 | 14 |
| test_mcp_protocol.py | 16 | 0 | 16 |
| test_tools_safe_exec_retry.py | 16 | 0 | 16 |
| test_tools_vuln_reasoning_cot.py | 16 | 0 | 16 |
| test_tools_vuln_knowledge.py | 19 | 0 | 19 |
| test_tools_data_facility.py | 21 | 0 | 21 |
| test_agent_brain_coverage.py | 130 | 0 | 130 |
| test_scanning_prompt_builder.py | 118 | 0 | 118 |
| test_mcp_server.py | 7 | 0 | 7 |
| test_core_orchestrator.py | 9 | 0 | 9 |
| test_mcp_manager.py | 9 | 0 | 9 |
| test_command_mcp_runner.py | 6 | 0 | 6 |
| **Root subtotal** | **1,636** | **0** | **1,636** |

### 4b. `tests/brutal/test_*_brutal.py` (5 files, 1,406 test functions: 991 sync + 415 async)

| File | sync | async | Total |
|---|---:|---:|---:|
| test_docker_brutal.py | 200 | 178 | **378** |
| test_kg_flows_providers_brutal.py | 211 | 131 | **342** |
| test_integration_security_brutal.py | 208 | 45 | **253** |
| test_api_auth_brutal.py | 232 | 1 | **233** |
| test_agents_brutal.py | 140 | 60 | **200** |
| **Brutal subtotal** | **991** | **415** | **1,406** |

### 4c. Grand total
- Root: 1,636 (all sync)
- Brutal: 1,406 (991 sync + 415 async)
- **TOTAL: 3,042 test functions across 50 test files**

> Note: 3,042 counts each `def test_` / `async def test_` line. Includes class-method tests (indented `def test_` inside test classes). All 415 async tests live in `brutal/`; the root suite is 100% synchronous.

---

## 5. `elengenix` Import Analysis

### 5a. Files importing directly from `elengenix` — **35 of 50 test files (70%)**

Grep pattern: `^\s*(from\s+elengenix|import\s+elengenix)`

**Root test files importing elengenix (30):**
test_scanning_decision_engine, test_scanning_vuln_reasoning_phase, test_scanning_hypothesis_boost, test_elengix_agent_memory, test_scanning_strategist, test_scanning_planner, test_brain, test_constitution_engine, test_elengix_governance, test_vuln_agent, test_scanning_specialist, test_scanning_scan_context, test_scanning_critic, test_scanning_agent_council, test_scanning_universal, test_scanning_intent, test_elengix_paths, test_scanning_modes, test_scanning_scan_loop, test_scanning_helpers, test_scanning_executor, test_scanning_prompt_builder, test_scanning_worker, test_loop, test_agent_tools, test_agent_agent_skills, test_scanning_tui_game, test_scanning_conversation, test_scanning_post_processor, test_elengix_scope

**Brutal test files importing elengenix (5 / 5 = 100%):**
test_api_auth_brutal, test_agents_brutal, test_docker_brutal, test_integration_security_brutal, test_kg_flows_providers_brutal

### 5b. Test files NOT importing elengenix directly (15)

These test modules import from other namespaces (MCP, tools, brain, agents) or use mocks:

| File | Likely target module |
|---|---|
| test_brain_coverage_gap.py | brain/coverage (mocked) |
| test_command_mcp_runner.py | command_mcp |
| test_mcp_client.py | mcp.client |
| test_mcp_protocol.py | mcp.protocol |
| test_mcp_config.py | mcp.config |
| test_mcp_server.py | mcp.server |
| test_mcp_manager.py | mcp.manager |
| test_core_orchestrator.py | core.orchestrator |
| test_tools_tool_recommender.py | tools.tool_recommender |
| test_tools_vuln_knowledge.py | tools.vuln_knowledge |
| test_tools_safe_exec_retry.py | tools.safe_exec / retry |
| test_tools_data_facility.py | tools.data_facility |
| test_tools_vuln_reasoning_cot.py | tools.vuln_reasoning_cot |
| test_agent_brain_coverage.py | agent.brain_coverage |
| test_brain_coverage.py | brain.coverage |

### 5c. Broad `elengenix` textual references (case-insensitive): 43 `.py` files
(All 35 importers + 8 others that mention `elengenix` in strings/comments/docstrings without a top-level import — e.g. `vulnerable_target/app.py` uses `/tmp/elengenix_vuln.db` and mentions "Elengenix scanners" in its docstring.)

---

## 6. Brutal Tests Subdirectory (`tests/brutal/`)

**7 `.py` files total** — `__init__.py` (empty) + `conftest.py` (path bootstrap) + **5 test modules**:

| # | File | sync | async | Total | Theme |
|---|---|---:|---:|---:|---|
| 1 | test_docker_brutal.py | 200 | 178 | 378 | Docker / container integration |
| 2 | test_kg_flows_providers_brutal.py | 211 | 131 | 342 | Knowledge-graph flows + providers |
| 3 | test_integration_security_brutal.py | 208 | 45 | 253 | End-to-end security integration |
| 4 | test_api_auth_brutal.py | 232 | 1 | 233 | API authentication |
| 5 | test_agents_brutal.py | 140 | 60 | 200 | Agent subsystem integration |
| | **Total** | **991** | **415** | **1,406** | |

**Key observations:**
- Brutal tests account for **46.2% of all test functions** (1,406 / 3,042) despite being only 10% of test files (5 / 50).
- All 415 `async def test_*` in the entire suite live here — these are the only async tests.
- `test_docker_brutal.py` is the single largest test file (378 functions, 178 async) — likely requires Docker daemon and external services.
- All 5 brutal files import from `elengenix` directly.
- Brutal tests appear to be heavy integration / security validation tests (per the suffix `_brutal` and the file names).

---

## 7. Vulnerable Target (`tests/vulnerable_target/`)

**1 file:** `app.py` (356 lines)

**Purpose:** Deliberately vulnerable Flask application used as a scan target by Elengenix scanner tests.

**Per its module docstring, it intentionally embeds 10 vulnerability classes:**
1. SQL Injection — `/login`
2. Reflected XSS — `/search`
3. Stored XSS — `/comments`
4. IDOR/BOLA — `/api/user/<id>`
5. Mass Assignment — `/register` (role=admin)
6. SSTI — `/render`
7. JWT `alg=none` — `/api/jwt/verify`
8. Prototype pollution — `/api/merge`
9. Race condition — `/api/coupon/redeem`
10. Path traversal — `/download`

**Stack:** Flask + sqlite3 + PyJWT. Default port 5555 (env `PORT`). Uses `/tmp/elengenix_vuln.db`. Hardcoded weak `SECRET_KEY = "supersecretkey-12345"`. **Not a test file — no `def test_*`.** Should be excluded from pytest collection (or guarded) — verify `pytest.ini`/`pyproject.toml` config in Phase 1-C.

---

## 8. Test File Naming Convention (root, 45 files)

| Prefix | Count | Coverage area |
|---|---:|---|
| `test_scanning_*` | 20 | Scanning engine subsystem (decision, planner, executor, critic, etc.) |
| `test_mcp_*` | 5 | MCP client/server/protocol/config/manager |
| `test_tools_*` | 5 | Tool recommender, vuln knowledge, safe-exec, data facility, CoT reasoning |
| `test_elengix_*` | 4 | Elengix-specific: agent memory, governance, paths, scope |
| `test_agent_*` | 3 | Agent tools, skills, brain coverage |
| `test_brain*` | 3 | Brain core + coverage |
| `test_command_mcp_runner` | 1 | MCP command runner |
| `test_core_orchestrator` | 1 | Core orchestrator |
| `test_constitution_engine` | 1 | Constitution engine |
| `test_vuln_agent` | 1 | Vulnerability agent |
| `test_loop` | 1 | Main agent loop |
| **Total root test files** | **45** | |

---

## 9. Risks / Observations for Next Phases

1. **No shared fixtures.** Both `conftest.py` files only do `sys.path` setup. Test isolation/teardown likely relies on per-test boilerplate → high duplication risk. Worth auditing in a later phase.
2. **Package name drift.** `_pkg_helper.py` dynamically discovers the package dir by globbing `elen*` and falls back to `'elengix'`. Imports use `elengenix.*` but the on-disk package may be `elengix/`. This mismatch is a known audit finding — flag for Phase 1-C (config) and Phase 2 (package identity).
3. **Brutal tests need infra.** `test_docker_brutal.py` (378 tests, 178 async) almost certainly requires a running Docker daemon + possibly the `vulnerable_target/app.py` Flask server. CI gating implications.
4. **`vulnerable_target/app.py` may be collected by pytest** unless excluded via config — verify in Phase 1-C.
5. **`tests/ssa`** is a 0-byte file with no extension — likely an accidental artifact. Recommend removal.
6. **Async tests concentrated in brutal/** — root suite is fully sync. If async fixtures are needed later, both `conftest.py` files will need `pytest-asyncio` config + fixture additions.

---

## 10. Audit Trail

- Scan root: `/home/z/my-project/securagentx-work/tests/`
- Tool: `find` (via LS) + `Grep` (ripgrep)
- Patterns used:
  - `^\s*(async\s+)?def test_` → 3,042 matches / 50 files
  - `^\s*def\s+test_` → 2,627 matches / 50 files
  - `^\s*async\s+def\s+test_` → 415 matches / 5 files (all brutal)
  - `^\s*(from\s+elengenix|import\s+elengenix)` → 35 files
  - `elengenix` (case-insensitive) → 43 `.py` files + 1 `.md`
- Report written to: `/home/z/my-project/securagentx-work/audit/phase1-b-tests.md`
- Worklog appended at: `/home/z/my-project/worklog.md`
