# Phase 13-A — Fix `test_ensure_dirs_creates_all_dirs` failure

## Task
Fix the single failing test after the Elengenix → SecurAgentX rename:
`tests/test_securagentx_paths.py::TestEnsureDirs::test_ensure_dirs_creates_all_dirs`.

## Root Cause
The test module imports `SECURAGENTX_DIRS` at module level (line 13):

```python
from securagentx.paths import (
    ...
    SECURAGENTX_DIRS,
    ...
)
```

This binds the name `SECURAGENTX_DIRS` in the test module's namespace to the
**dict object** that existed at import time. When the test later runs
`patch("securagentx.paths.SECURAGENTX_DIRS", {...})`, `unittest.mock.patch`
swaps the **module attribute** on `securagentx.paths` — it does NOT touch the
test module's local binding. The `ensure_dirs()` function inside
`securagentx.paths` reads `SECURAGENTX_DIRS` via module globals at call time,
so it correctly iterates the patched dict and creates the tmp dirs. But the
test's assertion loop:

```python
for d in SECURAGENTX_DIRS.values():
    assert d.exists(), ...
```

iterated the **stale local binding** — the original `~/.securagentx/{data,
tools, reports, scripts, plugins}` dict — so the assertions checked host
paths instead of the tmp paths, failing on any clean host that lacks a
pre-existing `~/.securagentx/` tree.

## Fix
Reference the module attribute at runtime inside the patch block instead of
the stale import-time local binding.

### Before (tests/test_securagentx_paths.py, lines 114–127)
```python
class TestEnsureDirs:
    def test_ensure_dirs_creates_all_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("securagentx.paths.SECURAGENTX_DIRS", {
                "data": Path(tmp) / ".securagentx" / "data",
                "tools": Path(tmp) / ".securagentx" / "tools",
                "reports": Path(tmp) / ".securagentx" / "reports",
                "scripts": Path(tmp) / ".securagentx" / "scripts",
                "plugins": Path(tmp) / ".securagentx" / "plugins",
            }):
                from securagentx.paths import ensure_dirs
                ensure_dirs()
                for d in SECURAGENTX_DIRS.values():
                    assert d.exists(), f"{d} was not created"
```

### After
```python
class TestEnsureDirs:
    def test_ensure_dirs_creates_all_dirs(self):
        import securagentx.paths as _paths_mod
        with tempfile.TemporaryDirectory() as tmp:
            with patch("securagentx.paths.SECURAGENTX_DIRS", {
                "data": Path(tmp) / ".securagentx" / "data",
                "tools": Path(tmp) / ".securagentx" / "tools",
                "reports": Path(tmp) / ".securagentx" / "reports",
                "scripts": Path(tmp) / ".securagentx" / "scripts",
                "plugins": Path(tmp) / ".securagentx" / "plugins",
            }):
                from securagentx.paths import ensure_dirs
                ensure_dirs()
                # Reference the module attribute directly so we pick up the
                # patched dict. The module-level `from securagentx.paths import
                # SECURAGENTX_DIRS` at the top of this file binds the *original*
                # dict object into a local name, which the patch never updates.
                for d in _paths_mod.SECURAGENTX_DIRS.values():
                    assert d.exists(), f"{d} was not created"
```

The key change is `for d in SECURAGENTX_DIRS.values():` →
`for d in _paths_mod.SECURAGENTX_DIRS.values():`. Attribute access on the
module object is resolved at call time, so it returns whatever `patch` has
installed on `securagentx.paths.SECURAGENTX_DIRS` at that moment.

## Verification

### Targeted test
```
python3 -m pytest tests/test_securagentx_paths.py::TestEnsureDirs::test_ensure_dirs_creates_all_dirs -v --timeout=60 --tb=short
```
Result: **1 passed in 2.60s** ✅

### Full file (regression check)
```
python3 -m pytest tests/test_securagentx_paths.py -v --timeout=60 --tb=short
```
Result: **18 passed in 2.68s** ✅ — zero regressions across all 6 test
classes (`TestPathConstants`, `TestGetDataPath`, `TestGetReportsPath`,
`TestGetDataDir`, `TestGetLogDir`, `TestGetToolsPath`, `TestEnsureDirs`,
`TestFindEnv`, `TestFindConfig`).

## Notes
- No production source code (`securagentx/paths.py`) was modified — the
  `ensure_dirs()` function already read `SECURAGENTX_DIRS` via module globals
  at call time, so it behaved correctly under patching. The bug was purely a
  test-side stale-binding issue.
- The other tests in the same file that use `patch(...SECURAGENTX_DIRS...)`
  (`TestGetDataPath::test_creates_parent_dir`,
  `TestGetReportsPath::test_creates_dir`,
  `TestGetToolsPath::test_creates_parent_dir`) are unaffected because they
  call functions that internally reference the module attribute — they never
  re-read `SECURAGENTX_DIRS` through the test module's local binding.
- The same latent pattern (module-level `from x import Y` + later `patch("x.Y")`
  + later local `Y` reference) exists in only this one test in this file;
  no other tests in the repo hit it for `SECURAGENTX_DIRS`.

## Files Modified
- `tests/test_securagentx_paths.py` — `TestEnsureDirs::test_ensure_dirs_creates_all_dirs` (lines 114–132): added `import securagentx.paths as _paths_mod` and switched assertion loop to `_paths_mod.SECURAGENTX_DIRS.values()`, plus explanatory comment.

## Files Written
- `audit/phase13-a-fix-paths-test.md` (this file)
