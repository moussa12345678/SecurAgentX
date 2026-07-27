# Phase 14-E — CI Boot-Smoke Step Verification

**Task ID:** P14-E
**Agent:** general-purpose (P14-E)
**Scope:** Verify whether the CI boot-smoke step `python -m securagentx --help || securagentx --help || true` would succeed post-Elengenix→SecurAgentX rename, and consider whether to add real `--help` flag handling to `main.py`. Builds on the finding from P13-D that `main.py:main()` ignores `--help` and launches the interactive welcome wizard.

---

## 1. Objective

P13-D established that `main.py:main()` does not parse `--help`; it unconditionally calls `wizard.run_if_first_time()` which `input()`s an API key and raises `EOFError` when stdin is closed (the CI condition). The trailing `|| true` in ci.yml masks this to exit 0.

P14-E verifies:

1. `python -m securagentx --help` exit code in isolation.
2. `securagentx --help` (console-script entrypoint) exit code in isolation.
3. The full CI composite command `... || ... || true` exit code.
4. Whether `main.py` uses argparse (in which case `--help` *should* work) or a custom menu (in which case it needs fixing).
5. Recommendation on adding real `--help` handling.

---

## 2. Reproduction Commands & Results

### 2.1 `python -m securagentx --help` (in isolation)

```bash
cd /home/z/my-project/securagentx-work
echo "" | timeout 10 python3 -m securagentx --help > /tmp/p14e_pyhelp.out 2>&1
echo "python exit: $?"
```

**Exit code:** **1**

**First 5 stdout lines** (banner + welcome wizard header):
```
(blank)
  ███████╗██╗     ███████╗███╗   ██╗ ██████╗ ███████╗███╗   ██╗██╗██╗  ██╗
  ██╔════╝██║     ██╔════╝████╗  ██║██╔════╝ ██╔════╝████╗  ██║██║╚██╗██╔╝
  █████╗  ██║     █████╗  ██╔██╗ ██║██║  ███╗█████╗  ██╔██╗ ██║██║ ╚███╔╝
  ██╔══╝  ██║     ██╔══╝  ██║╚██╗██║██║   ██║██╔══╝  ██║╚██╗██║██║ ██╔╝╝
```

**Last 15 stderr lines** (root cause):
```
  File "/home/z/my-project/securagentx-work/securagentx/__main__.py", line 11, in <module>
    main()
  File "/home/z/my-project/securagentx-work/main.py", line 423, in main
    config = wizard.run_if_first_time()
  File "/home/z/my-project/securagentx-work/tools/welcome_wizard.py", line 453, in run_if_first_time
    return self.run_setup()
  File "/home/z/my-project/securagentx-work/tools/welcome_wizard.py", line 237, in run_setup
    ai_provider = self._configure_ai_provider()
  File "/home/z/my-project/securagentx-work/tools/welcome_wizard.py", line 354, in _configure_ai_provider
    key = input(f"\n  Paste {provider_name} API key (or Enter to skip): ").strip()
EOFError: EOF when reading a line
```

### 2.2 `securagentx --help` (console script, in isolation)

```bash
which securagentx   # → /home/z/.venv/bin/securagentx  (pip install -e . created the entrypoint)
echo "" | timeout 10 securagentx --help > /tmp/p14e_conshelp.out 2>&1
echo "console exit: $?"
```

**Exit code:** **1**

**Last 15 stderr lines** (same root cause, same traceback shape — only the top frame differs because the console-script wrapper invokes `sys.exit(main())` instead of bare `main()`):
```
    sys.exit(main())
  File "/home/z/my-project/securagentx-work/main.py", line 423, in main
    config = wizard.run_if_first_time()
  File "/home/z/my-project/securagentx-work/tools/welcome_wizard.py", line 453, in run_if_first_time
    return self.run_setup()
  File "/home/z/my-project/securagentx-work/tools/welcome_wizard.py", line 237, in run_setup
    ai_provider = self._configure_ai_provider()
  File "/home/z/my-project/securagentx-work/tools/welcome_wizard.py", line 354, in _configure_ai_provider
    key = input(f"\n  Paste {provider_name} API key (or Enter to skip): ").strip()
EOFError: EOF when reading a line
```

### 2.3 Full CI composite command

```bash
cd /home/z/my-project/securagentx-work
bash -c 'echo "" | timeout 10 python3 -m securagentx --help > /tmp/p14e_a.out 2>&1 || echo "" | timeout 10 securagentx --help > /tmp/p14e_b.out 2>&1 || true'
echo "Final exit: $?"
```

**Final exit:** **0** ✅

**Component exit codes (verified individually):**

| Stage | Command | Exit |
|---|---|---|
| A | `python3 -m securagentx --help` | 1 |
| B | `securagentx --help` (runs because A failed) | 1 |
| — | `true` (runs because B failed) | 0 |

The bash `||` short-circuit means B runs only if A fails, and `true` runs only if B fails. Since both A and B exit non-zero, `true` is reached and the composite's exit code is 0. **CI's boot-smoke step would PASS post-rename**, exactly as P13-D predicted.

---

## 3. Why `--help` Does Not Work (main.py internals)

`main.py` *does* use argparse (line 10 imports it; line 318 instantiates the parser), but with two idiosyncrasies that together defeat `--help`:

### 3.1 `add_help=False` (line 318)

```python
parser = argparse.ArgumentParser(description="SecurAgentX CLI", add_help=False)
```

The default argparse behaviour of intercepting `-h`/`--help` and exiting 0 with a usage message is **disabled**. Without this, `--help` would have worked out of the box.

### 3.2 `parse_known_args()` (line 386)

```python
args, _ = parser.parse_known_args()
```

`parse_known_args()` returns `(parsed_args, unknown_args)` and **silently swallows** unknown options rather than erroring. So `--help` lands in the throwaway `_` slot and is dropped. `args.command` keeps its default `"auto"`, the wizard code path runs unconditionally (line 419: `if args.command not in skip_welcome_commands`), and the interactive wizard then calls `input()` → `EOFError` on closed stdin.

### 3.3 No custom `--help` short-circuit

A `rg -n -- "\-\-help" main.py` search returned **zero hits** in `main.py`. The only "help" support is the positional `"help"` *command* (line 434: `if args.command == "help"` → prints `CommandSimplifier.get_help_text()`), which requires `securagentx help` (no dashes) and is irrelevant when the user types `securagentx --help`.

### 3.4 Summary table

| Question | Answer |
|---|---|
| Does main.py use argparse? | **Yes** (line 318) — but with `add_help=False`. |
| Does argparse intercept `--help`? | **No** — `add_help=False` disables the built-in `-h`/`--help` short-circuit. |
| Does `parse_known_args` reject `--help` as unknown? | **No** — it silently drops it into `_`. |
| Is there a custom `if "--help" in sys.argv` short-circuit? | **No** — `rg -- "--help" main.py` returns 0 hits. |
| What is the actual `--help` behaviour? | `--help` is swallowed, command defaults to `"auto"`, welcome wizard runs, `input()` raises `EOFError` on closed stdin, exit 1. |

**Effective argv handling model:** "argparse-based parser with custom menu, but `--help` is neither parsed by argparse (because `add_help=False`) nor short-circuited by the application code (no `sys.argv` check)." This is an awkward middle ground between the two pure models the task description listed.

---

## 4. Recommendation

### Should we add real `--help` handling? — **YES (low priority, non-blocking).**

**Rationale:**

1. **The boot-smoke step is currently a no-op.** The trailing `|| true` guarantees exit 0 regardless of `main.py`'s behaviour. CI "passes" even though it has not actually verified that:
   - the package imports cleanly,
   - the `securagentx` entrypoint is registered and resolvable,
   - the CLI is invocable without a TTY,
   - any version/banner/help text renders.
   The rename from Elengenix→SecurAgentX — which was the entire point of phases 11–13 — would have been silently broken at the entrypoint layer and CI would not have caught it. (P13-D's accidental discovery of the wizard EOFError proves the point: the boot-smoke step *would* have caught the bug if `|| true` were removed.)

2. **The fix is trivial and surgical.** A 4-line guard at the top of `main()` (before `show_banner()` / `wizard.run_if_first_time()`):
   ```python
   if "--help" in sys.argv or "-h" in sys.argv:
       from tools.auto_detector import CommandSimplifier
       print(CommandSimplifier.get_help_text())
       sys.exit(0)
   ```
   This re-uses the existing help-text renderer (the same one the `help` *command* uses at line 437), so no new content needs to be authored. It also runs *before* the wizard, so the interactive `input()` is never reached when `--help` is requested.

3. **Alternatively, flip `add_help=False` → `add_help=True`** on line 318. This is even smaller (single-character change), restores argparse's default `-h`/`--help` behaviour, and prints the parser's auto-generated usage. Downside: the auto-generated usage is bare-bones (positional `command` + `target` + the ~20 registered `--flag`s) and lacks the curated help text that `CommandSimplifier.get_help_text()` provides. The custom short-circuit (option 1) is preferred for user-facing quality.

4. **A second, independent improvement:** change `parse_known_args()` → `parse_args()` (line 386). This would cause argparse to *error* on unknown flags (exit 2) rather than silently dropping them — currently `securagentx --typo-foo` is treated identically to `securagentx` (auto/TUI mode), which is a usability footgun. This is a separate concern from `--help` and is **not** required to fix the boot-smoke issue, but is worth tracking as a follow-up.

5. **If you would rather not touch `main.py` at all,** an alternative CI-side fix is to replace the boot-smoke command with a real smoke test that exercises import + entrypoint without launching the wizard:
   ```yaml
   # Option A: import-only smoke (cheapest, verifies package metadata)
   python -c "import securagentx; print(securagentx.__name__, 'importable')"
   # Option B: exercise the entrypoint with a no-op subcommand
   securagentx doctor --help 2>&1 | head -1
   # Option C: keep current command but drop the || true and rely on the main.py fix
   python -m securagentx --help
   ```
   Option A is the minimum viable smoke; Option C turns the existing step into a real gate. Either is preferable to the current `... || ... || true` cosmetic.

**Severity / priority:** Low. The current `|| true` makes this **non-blocking** — CI does not fail. The risk is *false-positive green* (CI passes while the CLI is actually broken), not a release blocker. Recommend tracking as P14-F or similar, paired with the test-pollution fix from P13-D's Issue B.

---

## 5. Files Touched

- `/home/z/my-project/securagentx-work/audit/phase14-e-boot-smoke.md` (this file) — new.
- `/tmp/p14e_pyhelp.out`, `/tmp/p14e_conshelp.out`, `/tmp/p14e_a.out`, `/tmp/p14e_b.out` — temporary scratch files (not part of deliverable).

**No production source files modified.** **No test files modified.** **No workflow files modified.** Pure verification deliverable.

---

## 6. Cross-Task Dependencies

- **Upstream:** P13-D (CI workflow logic verification — established that `--help` is ignored and the wizard crashes with `EOFError` on closed stdin; identified the `|| true` masking). P11-B (pyproject `[project.scripts]` entrypoint `securagentx = "main:main"` registers correctly — verified here by `which securagentx` → `/home/z/.venv/bin/securagentx`).
- **Downstream:**
  - **P14-F (recommended, low priority):** Apply the 4-line `--help` short-circuit to `main.py:main()` (option 1 in §4) AND/OR flip `add_help=False` → `add_help=True` (option 2). Then drop the trailing `|| true` from `.github/workflows/ci.yml:42-43` so the boot-smoke step becomes a real gate. Pair with P13-D Issue B (test-pollution fix) and P13-F (mark `test_agent_tools.py::TestAnalyzeSecurity` as `@pytest.mark.integration`) to get both workflows fully green on the next push to `main`.

---

## 7. Final Summary (Answers to Task Questions)

| Question | Answer |
|---|---|
| Does `python -m securagentx --help` exit 0 on its own? | **NO** — exits **1** with `EOFError` from `welcome_wizard._configure_ai_provider()` (stdin closed in CI). |
| Does the full CI command `... \|\| ... \|\| true` exit 0? | **YES** — bash `||` short-circuit: both `python -m securagentx --help` (exit 1) and `securagentx --help` (exit 1) fall through to the trailing `true`, giving composite exit 0. |
| Does main.py use argparse or a custom menu? | **Argparse-based parser (line 318) with `add_help=False` and `parse_known_args()` (line 386)**, plus a custom `command` dispatch. Neither argparse's built-in `-h`/`--help` short-circuit nor any application-level `sys.argv` check for `--help` exists, so `--help` is silently dropped and the welcome wizard runs. (This is an awkward hybrid of the two pure models — "uses argparse" but the `--help` path is effectively custom-and-broken.) |
| Recommendation: add real `--help` handling? | **YES (low priority, non-blocking)** — the current `|| true` makes the boot-smoke step a no-op; CI passes even when the CLI is broken. A 4-line `if "--help" in sys.argv or "-h" in sys.argv` guard at the top of `main()` (or flipping `add_help=False → True` on line 318) plus dropping `|| true` from ci.yml would turn it into a real gate. Trivial cost, real signal gain. Track as P14-F. |
