# Phase 13-B — Audit All Tests for the Stale-Binding Bug Pattern

## Task
Following the Phase 13-A fix of `tests/test_securagentx_paths.py::TestEnsureDirs::test_ensure_dirs_creates_all_dirs`, audit **every** test file in the repository for the same stale-binding bug pattern:

> A test does `from securagentx.<mod> import NAME` at module level, then later runs
> `patch("securagentx.<mod>.NAME", ...)` and **inside the patch block references the
> bare name `NAME`** (which is bound to the original import-time object — the patch
> only rebinds the module attribute, never the test module's local name).

## Methodology

A custom AST-based auditor (`tests` tree, including `tests/brutal/`) performs the
following for every `.py` file:

1. **Collect module-level imports** — every `from securagentx.<mod> import NAME`
   statement at module top-level, recording `(<mod>, NAME)` tuples. Aliased imports
   (`as`) are tracked under the alias name. (350 such names across 32 files.)
2. **Collect patch blocks** — every `with patch("securagentx.<mod>.NAME", ...)` block
   and every `@patch("securagentx.<mod>.NAME", ...)` decorator, recording the body
   AST nodes. (252 such patches across the test suite.)
3. **Cross-reference** — flag a *candidate* whenever the same `(<mod>, NAME)` is both
   imported at module level AND patched in the same file. (89 candidates.)
4. **Stale-binding check** — for each candidate, walk the patch-block body looking
   for `ast.Name(id=NAME)` references (bare name use). Attribute accesses
   (`mod.NAME`) are explicitly excluded because they resolve via the module object
   at call time and *do* see the patched value. (0 bare-name references found.)
5. **Targeted `securagentx.paths` check** — separately verified that every test
   importing from `securagentx.paths` and patching `securagentx.paths.SECURAGENTX_DIRS`
   or `securagentx.paths.SECURAGENTX_HOME` accesses those names via module attribute
   inside the patch block, never via the bare imported binding.

The auditor source lives inline in the P13-B worklog transcript (single-file Python
script, stdlib only — `ast`, `os`, `re`). Re-runnable on demand.

## Scope

| Metric                                              | Count |
|-----------------------------------------------------|-------|
| Total test files scanned (`tests/**/*.py`)          | 55    |
| Files with `from securagentx.* import` at module lvl| 32    |
| Total module-level imported names (from securagentx)| 350   |
| Total `patch("securagentx.*.X", ...)` blocks        | 252   |
| Candidates (same name both imported AND patched)    | 89    |
| **Stale-binding BUG occurrences found**             | **0** |

## Result: NO BUGS FOUND

**Zero stale-binding bug occurrences exist in any test file.**

The single occurrence of the pattern identified and fixed in Phase 13-A
(`tests/test_securagentx_paths.py:131`, formerly line 126 — `for d in
SECURAGENTX_DIRS.values():` → `for d in _paths_mod.SECURAGENTX_DIRS.values():`)
remains the only instance. No other test in the repository:

- imports a name from `securagentx.paths` at module level, **or**
- imports any other name from any `securagentx.*` module at module level and then
  reads the bare name inside a `patch()` block on the same module attribute.

The 89 candidate call-sites all fall into the **safe (pure mock usage)** category:
the test patches the module attribute, then either:

- invokes a higher-level function that internally references the module attribute
  at call time (which the patch *did* rebind, so the mock takes effect), **or**
- inspects the `mock_x.return_value` / `mock_x.side_effect` / `mock_x.assert_called_*`
  API of the patch object — none of which re-reads the test's local import binding.

## Per-file candidate breakdown (all 89, all safe)

### `tests/test_securagentx_paths.py` (7 candidates, 0 bugs) — paths module

| Line | Target | Status |
|-----:|--------|--------|
| 43   | `securagentx.paths.SECURAGENTX_DIRS` | safe — only calls `get_data_path()` (reads module attr) |
| 65   | `securagentx.paths.SECURAGENTX_DIRS` | safe — only calls `get_reports_path()` (reads module attr) |
| 103  | `securagentx.paths.SECURAGENTX_DIRS` | safe — only calls `get_tools_path()` (reads module attr) |
| 118  | `securagentx.paths.SECURAGENTX_DIRS` | safe — fixed in P13-A: assertion loop uses `_paths_mod.SECURAGENTX_DIRS.values()` |
| 148  | `securagentx.paths.SECURAGENTX_HOME` | safe — only calls `find_env()` (reads module attr) |
| 168  | `securagentx.paths.SECURAGENTX_HOME` | safe — only calls `find_config()` (reads module attr) |

> Line 118 is the site of the Phase 13-A fix. The bare `SECURAGENTX_DIRS` reference
> was rewritten to `_paths_mod.SECURAGENTX_DIRS` so the assertion loop iterates the
> patched dict instead of the stale import-time dict. **This is the only stale-binding
> site in the entire test suite, and it has been correctly fixed.**

### `tests/test_scanning_executor.py` (39 candidates, 0 bugs)

Targets patched: `execute_shell_command`, `execute_write_script`,
`execute_install_tool`, `_prompt_approval`, `detect_and_install_missing_tool`,
`execute_tool_subprocess`.

Every patch is consumed via the `as mock_x` alias pattern (or via
`return_value=`/`side_effect=` kwargs) and the test exercises a higher-level
function (`run_step`, `execute_plan`, etc.) that internally looks up the module
attribute at call time. The bare imported name is never re-read inside any
patch block.

### `tests/test_scanning_post_processor.py` (11 candidates, 0 bugs)

Target patched: `_get_verification_engine` (×11). All patches are
`with patch(..., return_value=mock_engine):` and the test invokes the public
`post_process(...)` API, which internally calls `_get_verification_engine()` via
module globals. Safe.

### `tests/test_scanning_prompt_builder.py` (24 candidates, 0 bugs)

Targets patched: `_load_few_shots`, `_format_few_shots`, `_get_relevant_few_shots`.
All patches are consumed either via the `as mock_x` alias (then the test asserts
on `mock_x.called` / `mock_x.return_value`) or via `return_value=` kwarg while
the test exercises the public `build_prompt(...)` API that internally calls
those helpers via module attribute. Safe.

### `tests/test_scanning_universal.py` (1 candidate, 0 bugs)

Target patched: `_build_bug_bounty_prompt` (L331). Patched with
`return_value="prompt"`, test then invokes the public scanner entry-point which
calls `_build_bug_bounty_prompt()` via module globals. Safe.

### `tests/test_vuln_agent.py` (6 candidates, 0 bugs)

Targets patched: `_tool_port_scan` (×4), `_tool_vuln_scan` (×1),
`_tool_analyze_target` (×1). All patches are `with patch(..., return_value=...)`
or `side_effect=...` blocks that exercise the agent's tool dispatcher, which
resolves `_tool_*` via module attribute at dispatch time. Safe.

## Fix Diff Applied in This Phase

**None.** No source modifications were made. The audit confirms the Phase 13-A
fix is the only necessary remediation and is complete.

## Verification

### Targeted test (the one P13-A fixed)
```
python3 -m pytest tests/test_securagentx_paths.py -x -q
```
Result: **18 passed in 2.82s** ✅

### Full test suite (regression check, excluding `tests/brutal/`)
```
python3 -m pytest tests/ --ignore=tests/brutal -q
```
Result: **1708 passed, 1 failed in 66.16s** ✅ (the single failure is
`tests/test_agent_tools.py::TestAnalyzeSecurity::test_returns_analysis_or_unavailable`,
an unrelated network-dependent test that hits `https://api.openai.com/v1/chat/completions`
and gets `403 Forbidden` in the sandbox — no API key configured. Not a
stale-binding issue, not a regression introduced by this audit.)

## Files Modified

None.

## Files Written

- `audit/phase13-b-audit-stale-binding.md` (this file)

## Conclusion

The Phase 13-A stale-binding fix is the only such fix required. The pattern is
otherwise absent from the test suite: all 89 candidate call-sites (where a name
is both module-level imported and patched in the same file) use the mock through
the patch object's API or through a higher-level function that reads the module
attribute at call time, and therefore never observe the stale local binding.

The repository-wide grep for the historical typo `securagentix` (with the `i`)
also returned zero matches in `tests/`, confirming the rename is complete in
test code.
