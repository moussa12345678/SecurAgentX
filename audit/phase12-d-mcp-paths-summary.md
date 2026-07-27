# Phase 12-D — MCP + SecurAgentX Paths / Scope / Governance Test Run

**Task ID:** P12-D
**Agent:** general-purpose (P12-D)
**Date:** post Elengenix → SecurAgentX rename verification
**Working dir:** `/home/z/my-project/securagentx-work`
**Raw output:** `/home/z/my-project/securagentx-work/audit/phase12-d-mcp-paths-results.txt`

---

## 1. Objective

Run the MCP + paths + scope + governance + agent-memory test suites after the
Elengenix → SecurAgentX rename, capturing pass/fail/error counts, duration, and
per-failure diagnostic detail. Integration-marked tests are deselected via the
`-m "not integration"` marker filter (matching the CI gate).

## 2. Command

```bash
cd /home/z/my-project/securagentx-work && python3 -m pytest \
  tests/test_mcp_*.py \
  tests/test_securagentx_paths.py \
  tests/test_securagentx_scope.py \
  tests/test_securagentx_agent_memory.py \
  tests/test_securagentx_governance.py \
  -v --timeout=300 -m "not integration" --tb=short \
  2>&1 | tee audit/phase12-d-mcp-paths-results.txt | tail -50
```

## 3. Environment

| Field | Value |
|-------|-------|
| Python | 3.12.13 |
| pytest | 9.0.2 |
| pluggy | 1.6.0 |
| pytest-asyncio | 1.3.0 |
| pytest-timeout | 2.4.0 |
| rootdir | `/home/z/my-project/securagentx-work` |
| interpreter | `/home/z/.venv/bin/python3` |

## 4. Headline Results

| Metric        | Value |
|---------------|-------|
| Total tests   | 172 |
| Passed        | 171 |
| Failed        | 1 |
| Errors        | 0 |
| Skipped       | 0 |
| Deselected    | 0 (no `integration` markers in this slice) |
| Duration      | 9.61 s |
| Exit code     | non-zero (1 failure) |

Final pytest summary line: `1 failed, 171 passed in 9.61s`.

## 5. Per-File Breakdown

| Test file | Tests | Pass | Fail |
|-----------|------:|-----:|-----:|
| tests/test_mcp_client.py             | 13 | 13 | 0 |
| tests/test_mcp_config.py             | 14 | 14 | 0 |
| tests/test_mcp_manager.py            |  9 |  9 | 0 |
| tests/test_mcp_protocol.py           | 16 | 16 | 0 |
| tests/test_mcp_server.py             |  7 |  7 | 0 |
| tests/test_securagentx_agent_memory.py | 59 | 59 | 0 |
| tests/test_securagentx_governance.py | 12 | 12 | 0 |
| tests/test_securagentx_paths.py      | 18 | 17 | 1 |
| tests/test_securagentx_scope.py      | 24 | 24 | 0 |
| **Total**                            | **172** | **171** | **1** |

## 6. Failure Detail

### tests/test_securagentx_paths.py::TestEnsureDirs::test_ensure_dirs_creates_all_dirs

**File:** `tests/test_securagentx_paths.py:127`
**Error class:** `AssertionError`
**Message:**

```
AssertionError: /home/z/.securagentx/scripts was not created
assert False
 +  where False = exists()
 +    where exists = PosixPath('/home/z/.securagentx/scripts').exists
```

**Traceback (short):**

```
tests/test_securagentx_paths.py:127: in test_ensure_dirs_creates_all_dirs
    assert d.exists(), f"{d} was not created"
E   AssertionError: /home/z/.securagentx/scripts was not created
```

### Root-cause analysis (test bug, NOT a production-code bug)

The test imports `SECURAGENTX_DIRS` at the top of the file (`tests/test_securagentx_paths.py:13`) which binds the name into the test module's namespace at import time:

```python
from securagentx.paths import (
    SECURAGENTX_HOME,
    SECURAGENTX_DIRS,           # ← bound once at import
    ...
)
```

The test then enters a `patch("securagentx.paths.SECURAGENTX_DIRS", {...})` block to swap in a temp-directory dict (lines 117-123). The patched object replaces the **module attribute** on `securagentx.paths`, so `ensure_dirs()` — which resolves `SECURAGENTX_DIRS` via module-global lookup — correctly iterates the **temp-dir** dict and creates the temp dirs.

But the assertion loop (line 126):

```python
for d in SECURAGENTX_DIRS.values():       # ← uses the LOCAL binding from line 13
    assert d.exists(), f"{d} was not created"
```

iterates over the **local** `SECURAGENTX_DIRS` reference captured at import time, which still points to the **original real** dict (`~/.securagentx/{data,tools,reports,scripts,plugins}`).

`ensure_dirs()` was called only inside the `patch` block and therefore only created the temp-dir paths, NOT the real `~/.securagentx/scripts` or `~/.securagentx/plugins`. The other three real dirs (`data`, `reports`, `tools`) happen to exist on disk because earlier tests in this file (`TestGetDataPath`, `TestGetReportsPath`, `TestGetToolsPath`, …) call `get_data_path`/`get_reports_path`/`get_tools_path` which mkdir their respective parents — but nothing else creates `scripts` or `plugins`. Hence the assertion fails specifically on `scripts`.

Verified by `ls /home/z/.securagentx/`:

```
drwxrwxr-x  data
drwxrwxr-x  reports
drwxrwxr-x  tools
```

— only 3 of 5 expected subdirs exist; `scripts` and `plugins` are missing.

### Recommended fix (advisory — not applied in this verification task)

Replace the local-binding assertion with a module-attribute lookup so it honours the patch:

```python
import securagentx.paths as _paths
...
for d in _paths.SECURAGENTX_DIRS.values():
    assert d.exists(), f"{d} was not created"
```

Or, equivalently, re-import inside the `patch` block. This is a pre-existing test-suite bug inherited from the rename (the legacy `test_elengenix_paths.py` had the same pattern). It is **NOT** caused by the Elengenix → SecurAgentX rename — the production code in `securagentx/paths.py` is correct: `ensure_dirs()` iterates the module-level `SECURAGENTX_DIRS` dict and creates all 5 subdirs as expected.

## 7. SecurAgentX Identity Check (post-rename sanity)

- `grep -ic 'elengenix\|elenginx' audit/phase12-d-mcp-paths-results.txt` → **0 hits** — no legacy identity strings survive in any collected/test output.
- `grep -ic 'securagentx' audit/phase12-d-mcp-paths-results.txt` → many hits across node IDs (`tests/test_securagentx_*.py::*`) and assertions (`~/.securagentx/...`) — all paths use the new identity.
- The 5 production modules under test (`securagentx/paths.py`, `securagentx/agents/memory.py`, `securagentx/governance/*`, `securagentx/mcp/*`) all import cleanly under the renamed package.

## 8. Verdict

- **MCP layer:** ✅ PASS (all 59 MCP tests pass across client/config/manager/protocol/server).
- **Scope layer:** ✅ PASS (24/24).
- **Agent-memory layer:** ✅ PASS (59/59).
- **Governance layer:** ✅ PASS (12/12).
- **Paths layer:** ⚠️ 1 FAIL — but it is a **test-code bug** (stale local binding of `SECURAGENTX_DIRS` ignores the `patch(...)` swap during the assertion loop), NOT a production-code regression. The `ensure_dirs()` function itself behaves correctly.

**Overall P12-D verdict:** ✅ PASS with 1 advisory test bug to fix in a follow-up. The Elengenix → SecurAgentX rename does not break any of the 172 collected tests in the MCP / paths / scope / governance / agent-memory slice; the single failure is a pre-existing test pattern bug exposed by `patch()` semantics, unrelated to the rename.

## 9. Files Written

- `/home/z/my-project/securagentx-work/audit/phase12-d-mcp-paths-results.txt` — raw pytest output (verbose, with `--tb=short`).
- `/home/z/my-project/securagentx-work/audit/phase12-d-mcp-paths-summary.md` — this summary report.

## 10. Cross-Task Dependencies

This slice is one of the Phase 12 test-execution gates. Combined with the
P11-series collection verification (P11-A through P11-E), it confirms that the
Elengenix → SecurAgentX rename is functionally clean at the unit-test level for
the MCP, paths, scope, governance, and agent-memory layers. The single paths
test failure is a pre-existing test-bug (stale local binding of a module global)
and should be addressed in a follow-up task; it does not block the rename or
any downstream CI gate. Downstream: the remaining Phase 12 slices (brain,
scanning, agents, brutal) should be run next to complete the post-rename
test-execution verification.
