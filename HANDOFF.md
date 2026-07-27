# HANDOFF — SecurAgentX Test Coverage Push (for next agent / Claude)

**Project**: /home/aponith/SecurAgentX
**Package**: `securagentx` (e-l-e-n-g-e-n-i-x, 9 chars) — NOT `securagentx` (7 chars, WRONG)
**Venv**: `venv/bin/python3`
**Test runner**: `pytest` (config in pyproject.toml)

---

## ⚠️ CRITICAL: Package Name Spelling

The correct package name is **`securagentx`** (9 chars). Two spellings exist in the wild and
the wrong one (`securagentx`, 7 chars) causes `ModuleNotFoundError`.

Byte-verify when in doubt:
```bash
python3 -c "import os; pkg=[e for e in os.listdir('.') if e.startswith('elen') and os.path.isdir(e) and not e.endswith('.egg-info')][0]; print(repr(pkg), [hex(ord(c)) for c in pkg])"
# → should print: 'securagentx' [..., '0x67', '0x65', '0x6e', '0x69', '0x78']  (g-e-n-i-x)
#   WRONG would show: 'securagentx' [..., '0x67', '0x69', '0x78']  (g-i-x, missing 0x65 0x6e = "en")
```

**ALWAYS** import as `from securagentx.X import Y` (9 chars). When measuring coverage, use
`--cov=securagentx` (9 chars) — `--cov=securagentx` silently collects ZERO data with no error.

---

## Current State (as of handoff)

### Full test suite: 1060 passed
Run: `cd /home/aponith/SecurAgentX && timeout 120 venv/bin/python3 -m pytest tests/ -q --tb=line --ignore=tests/test_securagentx_agent_memory.py -p no:timeout`

### Coverage: 57% TOTAL (was ~44% at start)
Measured with:
```bash
cd /home/aponith/SecurAgentX
venv/bin/python3 -m coverage run --source=securagentx -m pytest tests/ --ignore=tests/test_securagentx_agent_memory.py -q -p no:timeout
venv/bin/python3 -m coverage report --omit="*/hybrid_agent.py,*/logger.py"
```
(Note: `hybrid_agent.py` and `logger.py` in `securagentx/scanning/` have SyntaxErrors and
cannot be parsed by coverage — omit them.)

### Coverage by module (scanning core — DONE ✅)
| Module | Coverage | Status |
|--------|----------|--------|
| securagentx/scanning/executor.py | 97% | ✅ |
| securagentx/scanning/planner.py | 99% | ✅ |
| securagentx/scanning/post_processor.py | 99% | ✅ |
| securagentx/scanning/prompt_builder.py | 99% | ✅ |
| securagentx/scanning/hypothesis_boost.py | 100% | ✅ |
| securagentx/scanning/scan_context.py | 100% | ✅ |
| securagentx/scanning/scan_loop.py | 80% | ✅ |
| securagentx/scanning/helpers.py | 92% | ✅ |
| securagentx/scanning/decision_engine.py | 72% | ⚠️ (raise to 80+) |
| securagentx/scanning/vuln_reasoning_phase.py | 50% | ⚠️ |
| securagentx/scanning/intent.py | 79% | ⚠️ (close) |

### Coverage by module (other — NOT DONE)
| Module | Coverage | Lines |
|--------|----------|--------|
| securagentx/scanning/universal.py | 9% | 245 |
| securagentx/scanning/critic.py | 0% | 122 |
| securagentx/scanning/agent_council.py | 0% | 227 |
| securagentx/scanning/specialist.py | 0% | 172 |
| securagentx/scanning/strategist.py | 0% | 116 |
| securagentx/scanning/tui_game.py | 0% | 175 |
| securagentx/scanning/worker.py | 0% | 44 |
| securagentx/scanning/conversation.py | 0% | 88 |
| securagentx/scanning/modes.py | 0% | 62 |
| securagentx/scanning/hybrid_prompts.py | 0% | 7 |
| securagentx/agent/agent_memory.py | 28% | — |
| securagentx/agent/memory.py | 17% | — |
| securagentx/agent.py | 0% | — |
| securagentx/brain.py | 46% | — |
| securagentx/loop.py | 33% | — |
| securagentx/memory.py | 44% | — |
| securagentx/constitution_engine.py | 23% | — |

### Test files created this session (all passing)
- tests/test_scanning_executor.py (117 tests)
- tests/test_scanning_planner.py (100 tests)
- tests/test_scanning_decision_engine.py (30 tests)
- tests/test_scanning_post_processor.py (75 tests)
- tests/test_scanning_prompt_builder.py (118 tests)
- tests/test_scanning_scan_loop.py (fixed: added autouse mock for search_web to avoid real HTTP)
- tests/test_scanning_hypothesis_boost.py (13 tests)
- tests/test_scanning_scan_context.py (45 tests)
- tests/test_scanning_helpers.py (59 tests, pre-existing)

---

## Goal

Push coverage from 57% → **80%** on the `securagentx` package, then commit + push.

### Recommended priority order (highest impact first)
1. **scanning/vuln_reasoning_phase.py** (50→80, small, ~46 lines)
2. **scanning/intent.py** (79→90, tiny, ~43 lines)
3. **scanning/decision_engine.py** (72→80, ~176 lines)
4. **scanning/worker.py** (0→80, 44 lines — small win)
5. **scanning/modes.py** (0→80, 62 lines — small win)
6. **scanning/conversation.py** (0→80, 88 lines)
7. **scanning/critic.py** (0→80, 122 lines)
8. **scanning/specialist.py** (0→80, 172 lines)
9. **scanning/strategist.py** (0→80, 116 lines)
10. **scanning/agent_council.py** (0→80, 227 lines — large)
11. **scanning/universal.py** (9→80, 245 lines — large, may need network mocks)
12. **scanning/tui_game.py** (0→80, 175 lines — TUI, may be hard to test headlessly)
13. **agent/*.py** (memory.py 17%, agent_memory.py 28%, brain.py 46%, loop.py 33%, etc.)
14. **constitution_engine.py** (23%)

Items 11–14 are large. If 80% total is unreachable via scanning alone, also tackle
`securagentx/agent/` and `securagentx/constitution_engine.py`.

---

## Known Pitfalls (from securagentx-dev skill)

1. **Package spelling** — `securagentx` (9 chars). See top of file.
2. **Coverage spelling** — `--cov=securagentx` (9 chars). `--cov=securagentx` = no data.
3. **hybrid_agent.py / logger.py** — SyntaxErrors, omit from coverage report.
4. **AgentMemory testing** — use `sys.modules` pre-mock for `tools.vector_memory` and
   `tools.learning_engine` before importing `securagentx.agent.memory`. Add guard assertions.
5. **ToolResult category required** — `ToolResult(tool_name=..., success=..., category=ToolCategory.X, ...)`
   Omitting `category` → TypeError.
6. **Tool count test** — `test_all_25_tools_registered` checks `len(AVAILABLE_TOOLS) == 25`.
7. **Dynamic tool cleanup** — tests calling `_tool_create_tool` must clean up `_dynamic_tools`
   AND `AVAILABLE_TOOLS[:]` or later tests fail.
8. **Editable install refresh** — after adding new functions, run
   `pip install -e . --no-deps --quiet` to sync imports.
9. **6 warnings expected** (deprecation from legacy `agents/` module).
10. **No network in tests** — mock `search_web`, AI clients, subprocess.

---

## Commit/Push Workflow (when green)
```bash
cd /home/aponith/SecurAgentX
git add tests/test_scanning_*.py
git status
git commit -m "test: raise securagentx coverage to 80% (scanning core + agents)"
git push origin main
```

## Verification before commit
```bash
cd /home/aponith/SecurAgentX
timeout 120 venv/bin/python3 -m pytest tests/ -q --tb=line --ignore=tests/test_securagentx_agent_memory.py -p no:timeout
# confirm: 1060+ passed, 0 failed
timeout 120 venv/bin/python3 -m coverage run --source=securagentx -m pytest tests/ --ignore=tests/test_securagentx_agent_memory.py -q -p no:timeout
venv/bin/python3 -m coverage report --omit="*/hybrid_agent.py,*/logger.py" | grep TOTAL
# confirm: TOTAL >= 80%
```

---
*Handoff prepared by Hermes (kilo-auto/free) on 2026-07-14.*
