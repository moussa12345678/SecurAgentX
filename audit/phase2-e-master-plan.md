# Phase 2-E — Master Rename Plan

**Task ID:** P2-E
**Agent:** general-purpose (P2-E)
**Scope:** Synthesize P1-A..E + P2-A..D audit results into one executable rename plan for the `elengenix` → `securagentx` project rebrand.
**Date:** 2026-07-27

---

## 0. Executive Summary

| Metric | Value |
|---|---:|
| Total files containing `elengenix` (case-insensitive, ripgrep) | **478** |
| Files EXCLUDED from edits — coverage artifacts (`*,cover`) | 60 |
| Files EXCLUDED from edits — audit reports (phase1 `.md` + phase2 `.tsv`/`.md`) | 10 |
| **Files needing CONTENT edits** | **~408** |
| **Files needing FILENAME renames** | **2** (asset PNGs) |
| **Directories needing renames** | **1** (`elengenix/` → `securagentx/`) |
| Binary files preserved AS-IS (no edit, no rename) | 1 (tarball) |
| Files needing MANUAL review (not auto-edited) | 3 |

> The ~408 figure is a lower bound. After this master plan is written, three more `audit/phase2-*.tsv` files exist on disk; the script's `--glob '!audit/phase2-*'` exclusion handles them dynamically. A final re-verification pass should re-run `rg -l -i elengenix --glob '!audit/phase1-*' --glob '!audit/phase2-*' --glob '!*,cover'` and confirm the residual count is **0** after `--apply`.

---

## 1. Source Audit Reports Consulted

| Phase | File | Headline contribution |
|---|---|---|
| P1-A | `audit/phase1-a-scan.md` | 138 `.py` files in `elengenix/`; 80 files import `elengenix`; 246 import statements; `ELENGENIX_HOME` / `ELENGENIX_DIRS` constants in `paths.py`; `REPORTS_DIR` dead constant in `constants.py`. |
| P1-B | `audit/phase1-b-tests.md` | 55 `.py` files in `tests/`; 35 import `elengenix`; `_pkg_helper.py` uses dynamic `elen*` glob with fallback to misspelled `'elengix'`; `vulnerable_target/app.py` uses `/tmp/elengenix_vuln.db`. |
| P1-C | `audit/phase1-c-config.md` | `pyproject.toml` has 6 hits (name, author, console_script, 3 URLs); `.mcp.json` has 2 hardcoded `/mnt/data/Elengenix` paths; `.gitignore` has `elengenix.db`; `ci.yml` L42 boot-smoke test invokes both `python -m elengenix` and `elengenix --help`. |
| P1-D | `audit/phase1-d-docs.md` | 19 `.md` files (156 total occurrences); `HANDOFF.md` (50), `README.md` (32), `TOOL_CATALOG.md` (22), `CLAUDE.md` (12); badge URLs point at `moussa12345678/Elengenix`; asset filenames `elengenix.png`, `elengenix-red.png` flagged. |
| P1-E | `audit/phase1-e-aux.md` | 220 `.py` files in aux dirs (262 total files); 861 occurrences; `tools/` is densest (427/136); `main.py` has 91; `apply_to_fork.sh` has 27; tarball is binary (MD5 `de6bb4d88cfb7f131cd018547b1e5cd5`), do NOT modify. |
| P2-A | `audit/phase2-a-python-audit.tsv` | Per-Python-file occurrence counts; 386 rows (excludes `,cover` and audit outputs). Heaviest: `tests/brutal/test_kg_flows_providers_brutal.py` (405), `tests/brutal/test_integration_security_brutal.py` (283), `tests/test_scanning_executor.py` (98), `main.py` (91). |
| P2-B | `audit/phase2-b-markdown-audit.tsv` | 21 markdown rows; 5 are audit reports (excluded), 16 are rename targets. Case-variant breakdown: 232 lowercase + 86 Title + 11 uppercase across all `.md` files. |
| P2-C | `audit/phase2-c-config-audit.tsv` | 10 config files (18 occurrences); P0-critical: `pyproject.toml` (name/console_script/URLs), `.mcp.json` (hardcoded paths), `ci.yml` (CLI invocation). Case variants: 5 lowercase + 13 Title; 0 uppercase in config layer. |
| P2-D | `audit/phase2-d-shell-audit.tsv` | 10 shell/text files (48 occurrences); `apply_to_fork.sh` (27) and `apply_to_fork_termux.sh` (8) reference both the tarball filename AND `Elengenix` brand; SVG assets contain `<text>elengenix …</text>` and `<image href="…elengenix.png">`; 3 binary files with brand in filename (2 PNGs + 1 tarball). |

---

## 2. Case-Substitution Rules (exact from → to)

Apply **in this order** (longest exact-case match first to avoid prefix bugs; the three forms are disjoint so order is technically arbitrary, but uppercase-first is the safer convention):

| # | From (case-sensitive) | To (case-sensitive) | Examples (covers) |
|---:|---|---|---|
| 1 | `ELENGENIX` | `SECURAGENTX` | `ELENGENIX_HOME` → `SECURAGENTX_HOME`; `ELENGENIX_DIRS` → `SECURAGENTX_DIRS`; `tests/API_REFERENCE.md` line refs to `ELENGENIX` in README/docs. |
| 2 | `Elengenix` | `SecurAgentX` | `Elengenix Project` → `SecurAgentX Project`; `moussa12345678/Elengenix` → `moussa12345678/SecurAgentX`; `/mnt/data/Elengenix` → `/mnt/data/SecurAgentX`; `You are Elengenix AI` → `You are SecurAgentX AI`. |
| 3 | `elengenix` | `securagentx` | `from elengenix.X import Y` → `from securagentx.X import Y`; `import elengenix` → `import securagentx`; `elengenix.db` → `securagentx.db`; `~/.elengenix/` → `~/.securagentx/`; `elengenix = "main:main"` → `securagentx = "main:main"`; `elengenix.png` → `securagentx.png`; `python -m elengenix` → `python -m securagentx`; `elengenix --help` → `securagentx --help`. |

### Special contextual mappings (covered by the rules above)

| Context | From | To | Covered by rule |
|---|---|---|---:|
| Distribution / package name | `name = "elengenix"` | `name = "securagentx"` | #3 |
| Author label | `Elengenix Project` | `SecurAgentX Project` | #2 |
| Console script | `elengenix = "main:main"` | `securagentx = "main:main"` | #3 |
| GitHub URLs (Homepage / Repository / Issues / badge URLs) | `moussa12345678/Elengenix` | `moussa12345678/SecurAgentX` | #2 |
| Hardcoded MCP paths | `/mnt/data/Elengenix` | `/mnt/data/SecurAgentX` | #2 |
| DB filename pattern | `elengenix.db` | `securagentx.db` | #3 |
| User home dir | `~/.elengenix/` | `~/.securagentx/` | #3 |
| Asset filenames (PNG) | `elengenix.png` / `elengenix-red.png` | `securagentx.png` / `securagentx-red.png` | #3 |
| Package directory | `elengenix/` (dir name) | `securagentx/` | #3 (applied as dir rename, not sed) |
| Python module imports | `from elengenix.X` / `import elengenix.X` | `from securagentx.X` / `import securagentix.X` | #3 |

### Mixed-case forms NOT observed (verified by P2-B/C TSVs)
- `eLENGENIX`, `elengenixProject`, `elengenix_home` (snake_case var name), `ElengenixProject` (no-space) — **none found** in P2-B or P2-C case-variant enumeration.
- `_elengenix_home` local variable in `elengenix/agent/vuln_agent.py:1705` — covered by rule #3 (`elengenix` → `securagentx` becomes `_securagentx_home`).

---

## 3. Files Needing CONTENT Edits (≈ 408 files)

### 3.1 By area (reconciled across P2-A/B/C/D TSVs)

| Area | Files | Source TSV | Notes |
|---|---:|---|---|
| Python source (`.py`) | **386** | P2-A | Excludes `,cover` (regenerated) and audit outputs. 80 are inside `elengenix/` and have `from elengenix.*` self-imports. |
| Markdown (`.md`) | **16** | P2-B | 5 audit reports excluded; `MEMORY.md.example` also counted in P2-C (dedup). |
| Config / structured | **10** | P2-C | `pyproject.toml`, `.mcp.json`, `.gitignore`, `ci.yml`, `requirements.txt`, `.env.example`, `config.yaml.example`, `MEMORY.md.example` (overlap), 2× `examples/plugins/*/plugin.yaml`. |
| Shell / text / SVG | **6** | P2-D | `apply_to_fork.sh`, `apply_to_fork_termux.sh`, `prompts/system_prompt.txt`, `assets/color-cycle.svg`, `assets/typing-animation.svg`, `assets/logo-animated.svg`. (`.env.example`, `config.yaml.example`, `requirements.txt`, `MEMORY.md.example` are double-counted in P2-D — already in P2-C.) |

**Reconciled total (deduped): 386 + 16 + 10 + 6 − 4 overlaps (MEMORY.md.example in B/C/D; .env.example, config.yaml.example, requirements.txt in C/D) = ~414.**

The ripgrep authoritative count (after exclusions for `*,cover`, `audit/phase1-*.md`, `audit/phase2-*.tsv`, and the 1 phase2-a TSV that existed at scan time) is **412**. The ~2-file discrepancy vs the area-by-area sum (414) is due to small overlaps in how each TSV agent defined its filter set. **Use the script's `--dry-run` output for the authoritative edit list at execution time.**

### 3.2 Top 15 densest files (by occurrence count, from P2-A)

| File | Occurrences | Notes |
|---|---:|---|
| `tests/brutal/test_kg_flows_providers_brutal.py` | 405 | Heaviest single file. Patch with care — integration test. |
| `tests/brutal/test_integration_security_brutal.py` | 283 | |
| `tests/test_scanning_executor.py` | 98 | |
| `main.py` | 91 | CLI entry point. |
| `tests/test_elengix_paths.py` | 59 | Path-constant test; will need identifier renames (`ELENGENIX_HOME` → `SECURAGENTX_HOME`, etc.) AND the misspelled filename `test_elengix_*` should be considered for rename to `test_securagentx_*` (manual — out of scope for the auto script). |
| `tests/test_brain_coverage_gap.py` | 49 | |
| `tests/test_scanning_prompt_builder.py` | 41 | |
| `elengenix/providers/__init__.py` | 40 | Provider re-export hub. |
| `tests/brutal/test_docker_brutal.py` | 36 | Docker integration test. |
| `tools/command_suggest.py` | 36 | |
| `elengenix/paths.py` | 34 | Defines `ELENGENIX_HOME`, `ELENGENIX_DIRS`, `~/.elengenix`. |
| `tests/test_agent_brain_coverage.py` | 33 | |
| `tests/test_scanning_universal.py` | 32 | |
| `elengenix/agent/vuln_agent.py` | 29 | |
| `tools/auto_detector.py` | 28 | |

### 3.3 Critical files (P0 — breaking if not renamed correctly)

| File | Critical hits | Why critical |
|---|---|---|
| `pyproject.toml` | L6, L13, L87, L90-L92 | Distribution name, author label, console_script entry, 3 GitHub URLs. If `name` doesn't match the renamed `securagentx/` package dir, `pip install -e .` will fail. |
| `.mcp.json` | L9, L13 | Hardcoded `/mnt/data/Elengenix` paths for filesystem + git MCP servers. After rename, the host directory at `/mnt/data/Elengenix` must ALSO be renamed to `/mnt/data/SecurAgentX` (or the path arg updated to point to the existing location). |
| `.github/workflows/ci.yml` | L42 | Boot smoke test runs `python -m elengenix --help || elengenix --help || true`. Must become `python -m securagentx --help || securagentx --help || true`. |
| `elengenix/paths.py` | L18-L97 | Defines `ELENGENIX_HOME = Path("~/.elengenix")` and `ELENGENIX_DIRS`. The 80 files importing `from elengenix.paths import ELENGENIX_HOME` will break if `paths.py` is renamed but the importers are not. |
| `elengenix/__init__.py` | (per P1-A) | Re-exports `REPORTS_DIR` etc. All consumers must be updated in lock-step. |
| `elengenix/agent/vuln_agent.py` | L1705-L1707 | Hardcoded `Path("~/.elengenix")` outside `paths.py` — duplicate definition that must also be renamed for consistency. |
| `tests/_pkg_helper.py` | (per P1-B) | Uses dynamic `elen*` glob to discover package dir; falls back to misspelled `'elengix'`. After `elengenix/` → `securagentx/` rename, the `elen*` glob will FAIL. **Must be manually updated to `secur*` glob (or hardcode `'securagentx'`).** |

### 3.4 Coverage artifacts excluded (`*,cover`) — 60 files

Auto-generated pytest coverage data; regenerated by the test suite. Distribution: `elengenix/` (40), `mcp/` (6), `commands/` (6), `cli/` (5), `core/` (3). Do NOT edit; do NOT commit (recommend adding `*,cover` to `.gitignore` in a follow-up cleanup task).

### 3.5 Audit reports excluded — 10 files

| # | File | Reason |
|---:|---|---|
| 1-5 | `audit/phase1-{a,b,c,d,e}-*.md` | My own Phase 1 audit outputs (document the rename, not part of it). |
| 6-9 | `audit/phase2-{a,b,c,d}-*.tsv` | Sibling-agent Phase 2 audit TSVs. |
| 10 | `audit/phase2-e-master-plan.md` | This very file. |

---

## 4. Files Needing FILENAME Renames (2)

Only two files have `elengenix` in their **filename** and need to be renamed (the binary tarball is excluded — see §6):

| From | To | Notes |
|---|---|---|
| `assets/elengenix.png` | `assets/securagentx.png` | PNG logo, 770×260, 8-bit RGBA. Referenced by `assets/color-cycle.svg` L15 (`<image href="…">`) — the SVG href must also be updated (covered by content edits in §3.1). |
| `assets/elengenix-red.png` | `assets/securagentx-red.png` | PNG red-logo variant. Referenced by `assets/color-cycle.svg` L29 — same update needed. |

### Files whose filename contains `elengenix` but should NOT be renamed

| File | Reason |
|---|---|
| `elengenix-pentagi-integration.tar.gz` | Binary tarball (775,547 B, MD5 `de6bb4d88cfb7f131cd018547b1e5cd5`). KEEP AS-IS per explicit user instruction. The `ARCHIVE="elengenix-pentagi-integration.tar.gz"` constants in `apply_to_fork.sh` L16 and `apply_to_fork_termux.sh` L7 must ALSO be preserved (so the scripts continue to find the actual tarball). |

### Files whose filename contains `elengix` (MISSPELLING) — flagged for optional rename

Per P1-D observation: `tests/test_elengix_agent_memory.py`, `tests/test_elengix_governance.py`, `tests/test_elengix_paths.py`, `tests/test_elengix_scope.py`, `FIX_NOTES.md` (uses `elengix` not `elengenix`). These are NOT covered by the rename script (the script targets `elengenix`, not `elengix`). Recommend a **separate manual pass** to rename `test_elengix_*` → `test_securagentx_*` for consistency, AFTER the main rename completes.

---

## 5. Directories Needing Renames (1)

| From | To | Notes |
|---|---|---|
| `elengenix/` | `securagentx/` | Top-level package directory (138 `.py` files, 13 subpackages per P1-A). Only ONE directory named `elengenix` exists in the project tree (verified via glob `**/elengenix/**` — all matches are under this single root). |

### Why only 1 directory rename
- `~/.elengenix/` (referenced in code) is a **runtime user-home directory**, not a project-tree directory. The string `~/.elengenix/` → `~/.securagentx/` is a content edit (covered by §3, rule #3), and the actual home dir is created lazily by `paths.py` at first run.
- No `tests/elengenix/` or other nested `elengenix/` directory exists.
- `redteam_agent/` has 0 elengenix refs (P1-E) — no rename needed.

---

## 6. Risk Warnings

### 6.1 Binary / immutable artifacts (DO NOT TOUCH)

| Item | Action |
|---|---|
| `elengenix-pentagi-integration.tar.gz` (binary, 775 KB) | **KEEP AS-IS.** Filename AND bytes preserved. The script excludes this file from both content edits and filename renames via `EXCLUDE_GLOBS`. |
| `*,cover` coverage artifacts (60 files) | Exclude from edits — regenerated by pytest. Optionally add to `.gitignore` later. |
| `assets/elengenix.png`, `assets/elengenix-red.png` | Rename filename only; embedded logo pixels may still show old brand visually. Regenerating the raster image is OUT OF SCOPE for this text-rename audit. (Logo generation scripts: `scripts/gen_logo.py`, `scripts/gen_logo_clean.py`, `scripts/gen_logo_png.py` — these contain `elengenix` text refs that the rename script WILL update.) |

### 6.2 Git history

The `.git/` directory contains historical commits with `elengenix` in messages, branch names, and tracked paths. The rename script does NOT touch `.git/`. Two acceptable post-rename states:

- **Option A (recommended):** Accept historical mentions. Old commits retain `elengenix` branding as a historical record. New commits use `securagentx`. Clean separation at the rename commit.
- **Option B (aggressive):** Run `git filter-repo` (preferred over `filter-branch`) to rewrite history. This rewrites every commit hash, breaks all PRs/issues that reference commit SHAs, and requires force-push. **Only do this if the project has no external contributors or open PRs.** Out of scope for the rename script.

### 6.3 Hardcoded filesystem paths

`.mcp.json` L9 + L13 reference `/mnt/data/Elengenix`. After the rename, the host directory `/mnt/data/Elengenix` (if it exists on the dev box) must ALSO be renamed to `/mnt/data/SecurAgentX`, OR the `.mcp.json` path must be repointed to wherever the data actually lives. **The script will update the JSON content, but cannot rename host directories.** Verify post-rename that `ls /mnt/data/SecurAgentX` works (or symlink it back).

### 6.4 Cross-cutting Python identifiers

`ELENGENIX_HOME` and `ELENGENIX_DIRS` are Python module-level constants in `elengenix/paths.py`. They are imported by name (not via `from paths import *`) in:

- `elengenix/agent/agent_memory.py:15`
- `elengenix/agent/agent_skills.py:14`
- `elengenix/agent/vuln_agent.py` (multiple)
- `elengenix/paths.py` (definition)
- `tools/vector_memory.py:19`
- `main.py:26`
- `mcp/config.py:18`
- `tests/test_elengix_paths.py:12-13, 23, 28-33, 43, 65, 103, 117, 126, 143, 163` (heavy use)
- `tests/test_agent_agent_skills.py:29, 266, 297`
- `tests/brutal/conftest.py` (and likely others — re-verify post-rename)

The script's case-rule #1 (`ELENGENIX` → `SECURAGENTX`) handles ALL of these atomically, since both the definition and every import use the same uppercase form. **No separate identifier-rename pass needed.**

### 6.5 `tests/_pkg_helper.py` dynamic discovery (CRITICAL)

Per P1-B: `_pkg_helper.py` discovers the package dir at runtime by globbing `elen*` and falls back to the misspelled `'elengix'`. After the directory rename `elengenix/` → `securagentx/`:
- The `elen*` glob will FAIL to match anything.
- The fallback `'elengix'` is also wrong.

**Manual fix required (NOT auto-handled by the script):** Update `_pkg_helper.py` to glob `secur*` or hardcode `'securagentx'`. The script flags this file in `MANUAL_REVIEW_FILES` and does NOT auto-edit it.

### 6.6 `apply_to_fork.sh` and `apply_to_fork_termux.sh` (MANUAL)

These scripts contain 27 and 8 elengenix refs respectively (P2-D). They reference the tarball filename (`elengenix-pentagi-integration.tar.gz`) AND the `elengenix/` package directory AND `Elengenix` brand strings. A blind sed would:
- ✅ Correctly rename `Elengenix` brand strings (e.g., comment headers, "looks like an Elengenix repo")
- ✅ Correctly rename `elengenix/` directory references (e.g., L68 `elengenix/agent/vuln_agent.py`, L92-97 `elengenix/$dir/`)
- ❌ **BREAK** the `ARCHIVE="elengenix-pentagi-integration.tar.gz"` constant (L16, L7-termux) — the script would no longer find the actual tarball (which is preserved as-is per §6.1).

**Manual fix required:** After the auto-rename pass, restore the `ARCHIVE="elengenix-pentagi-integration.tar.gz"` line in both scripts (the `PATCH=` line and `BRANCH_NAME=feat/pentagi-integration` line can stay renamed since they don't reference the actual file). The script flags these in `MANUAL_REVIEW_FILES` and does NOT auto-edit them.

### 6.7 Auto-generated documentation

`docs/TOOL_CATALOG.md` (22 occurrences) is auto-generated from `tools/*.py` docstrings. The script WILL rename the existing markdown content, but if the catalog is regenerated later, the generator (likely a script in `scripts/`) must ALSO be updated. The rename script handles the generator scripts' content edits via the standard pass; regeneration post-rename should produce a `securagentx`-branded catalog.

### 6.8 Branch name in apply_to_fork.sh

`BRANCH_NAME="feat/pentagi-integration"` (L18) — contains `pentagi` but NOT `elengenix`. The script will not touch this line. Leave as-is.

### 6.9 Test count inconsistency

Per P1-D observation: README.md says 334 tests, CLAUDE.md says 379+, HANDOFF.md says 1060 passed. These are documentation claims, not code — the rename script will update the brand strings in these docs but will NOT reconcile the numbers. Recommend a separate documentation cleanup pass after the rename.

### 6.10 Mixed-language docs

`AGENTS.md`, `docs/compose/specs/2026-07-02-vuln-finder-design.md` contain Thai-language content. The rename script operates on ASCII case variants only (`ELENGENIX`, `Elengenix`, `elengenix`) and will not damage Thai Unicode characters. Verify post-rename that Thai sections still render correctly.

### 6.11 `pytest.ini` `--cov=elengenix` invocation

Per P1-D observation (line 188): there are `--cov=elengenix` invocations that need to become `--cov=securagentx`. The rename script handles these via rule #3. Verify by re-running `pytest --collect-only` post-rename.

---

## 7. Python Script Template

Saved to: **`audit/rename_template.py`** (self-contained, executable).

```python
#!/usr/bin/env python3
"""
elengenix → securagentx rename script (TEMPLATE — review before running).

Performs safe sed-like substitution using ripgrep for file enumeration,
with proper case-variant handling. Designed to be re-run safely; supports
--dry-run mode for verification.

Case-substitution rules (apply in this exact order):
    ELENGENIX  →  SECURAGENTX   (uppercase identifiers / headings)
    Elengenix  →  SecurAgentX   (Title-case prose, URLs, paths)
    elengenix  →  securagentx   (lowercase identifiers, imports, filenames)

Files excluded:
    *,cover                              (pytest coverage artifacts, regenerated)
    audit/phase1-*.md                    (Phase 1 audit reports)
    audit/phase2-*.tsv                   (Phase 2 audit TSVs)
    audit/phase2-*.md                    (Phase 2 audit markdown — incl. master plan)
    elengenix-pentagi-integration.tar.gz (binary tarball — KEEP AS-IS)

Files needing MANUAL handling (script REPORTS but does NOT auto-edit):
    apply_to_fork.sh              (preserve ARCHIVE= constant + tarball refs)
    apply_to_fork_termux.sh       (same — preserve ARCHIVE= constant)
    tests/_pkg_helper.py          (uses dynamic elen* glob — verify post-rename)

Usage:
    python3 rename_template.py --dry-run                    # preview only
    python3 rename_template.py --apply                      # perform edits
    python3 rename_template.py --apply --root /path/to/repo # custom root
"""
# (full script body lives in audit/rename_template.py — see that file)
```

### 7.1 Script design guarantees

1. **Ripgrep-backed enumeration** — uses `rg -l -i elengenix` so binary files (PNG, tarball) are auto-skipped via `--no-binary`. No accidental binary corruption.
2. **Exclusion via `--glob`** — cover artifacts and audit reports filtered at ripgrep level (fast, no Python filtering needed).
3. **Case-rule order matters** — `ELENGENIX` first (longest exact match), then `Elengenix`, then `elengenix`. The three forms are disjoint, so order is defensive only.
4. **`surrogateescape` encoding** — round-trips any non-UTF-8 bytes safely (relevant for SVG files with mixed Unicode).
5. **Idempotent** — running twice is safe: second run finds 0 matches and reports no edits.
6. **Dry-run first** — `--dry-run` prints every file + replacement count without modifying anything.
7. **Manual-review files flagged, not auto-edited** — `apply_to_fork*.sh` and `tests/_pkg_helper.py` are listed at end of run but skipped.
8. **Filename + directory renames are separate steps** — can be skipped via `--skip-filename-renames` / `--skip-directory-renames` to do content-only pass first.

### 7.2 Recommended execution order

```bash
# 1. Preview
cd /home/z/my-project/securagentx-work
python3 audit/rename_template.py --dry-run --root . | tee /tmp/dry-run.log

# 2. Review dry-run output; spot-check a few files
less /tmp/dry-run.log

# 3. Content-only pass first (safer; lets you re-run tests before committing to dir rename)
python3 audit/rename_template.py --apply --root . \
    --skip-filename-renames --skip-directory-renames

# 4. Run tests to verify imports resolve (will FAIL until step 5 completes)
#    At this point, `elengenix/` still exists; tests should still pass.
pytest --collect-only -q | head -50

# 5. Rename the package directory
python3 audit/rename_template.py --apply --root . --skip-filename-renames
#    (Step 3's --skip-directory-renames is now dropped, so dir rename happens.)

# 6. Manually fix tests/_pkg_helper.py (change `elen*` glob → `secur*`)
# 7. Manually fix apply_to_fork.sh + apply_to_fork_termux.sh (restore ARCHIVE= line)

# 8. Rename asset PNGs
python3 audit/rename_template.py --apply --root . --skip-directory-renames
#    (Step 5 already done; this pass does only the filename renames.)

# 9. Re-run tests
pytest -x

# 10. Verify zero residual elengenix refs (excluding audit reports + cover)
rg -l -i elengenix --glob '!audit/phase1-*' --glob '!audit/phase2-*' \
    --glob '!*,cover' --glob '!elengenix-pentagi-integration.tar.gz' .
#    Expected output: empty (or only apply_to_fork*.sh + _pkg_helper.py if not yet manually fixed)
```

---

## 8. Verification Checklist (post-rename)

- [ ] `rg -l -i elengenix` returns empty (excluding `audit/`, `*,cover`, and tarball).
- [ ] `python3 -c "import securagentix"` succeeds.
- [ ] `python3 -m securagentix --help` succeeds.
- [ ] `securagentix --help` succeeds (after `pip install -e .`).
- [ ] `pytest --collect-only` reports 0 collection errors.
- [ ] `pytest -x` passes (or fails only for pre-existing reasons unrelated to rename).
- [ ] `ls /mnt/data/SecurAgentX` exists OR `.mcp.json` updated to point to actual data dir.
- [ ] `tests/_pkg_helper.py` updated to glob `secur*`.
- [ ] `apply_to_fork.sh` ARCHIVE= line still references `elengenix-pentagi-integration.tar.gz`.
- [ ] `apply_to_fork_termux.sh` ARCHIVE= line still references `elengenix-pentagi-integration.tar.gz`.
- [ ] `assets/securagentx.png` and `assets/securagentx-red.png` exist (renamed).
- [ ] `assets/color-cycle.svg` L15 + L29 hrefs point to `securagentx.png` / `securagentx-red.png`.
- [ ] `pyproject.toml` `name = "securagentix"` and `elengenix-pentagi-integration.tar.gz` (tarball) preserved.
- [ ] `git status` shows expected file moves (including the `elengenix/` → `securagentx/` rename detected as a rename, not delete+add).
- [ ] `pip install -e .` succeeds with new package name.

---

## 9. Out-of-Scope Items (tracked for future phases)

| Item | Why deferred |
|---|---|
| Regenerate `assets/securagentx.png` raster logo | Out of scope — text-rename only. Visual redesign is a separate creative task. |
| Reconcile test-count claims (334 vs 379 vs 1060) in README/CLAUDE/HANDOFF | Documentation cleanup, not rename. |
| Decide fate of `HANDOFF.md`, `AGENT_REVIEW.md`, `FIX_NOTES.md` (temporal/internal docs) | Archive decision, not rename. |
| Rename `tests/test_elengix_*` (misspelled) → `tests/test_securagentx_*` | Misspelling cleanup; the rename script targets `elengenix` only, not `elengix`. |
| Add `*,cover` to `.gitignore` | Hygiene task, not rename. |
| Rewrite git history with `git filter-repo` | Per §6.2, only if no external contributors. Decision deferred to maintainer. |
| Reconcile CLAUDE.md vs README.md architecture claims (6-phase pipeline vs pipeline-removed) | Documentation reconciliation, not rename. |

---

## 10. Audit Trail

- Source audits: `audit/phase1-{a,b,c,d,e}-*.md` (5 files), `audit/phase2-{a,b,c,d}-*.tsv` (4 files).
- Master plan: `audit/phase2-e-master-plan.md` (this file).
- Rename script template: `audit/rename_template.py`.
- Worklog entry: appended to `/home/z/my-project/worklog.md` per template.
- Enumeration tool: ripgrep via the `Grep` tool (case-insensitive, all paths under `/home/z/my-project/securagentx-work/`).
- Cover-artifact count: 60 (verified via awk on ripgrep output).
- Audit-report count: 5 phase1 `.md` + 4 phase2 `.tsv` + 1 phase2 `.md` (this file) = 10 files excluded.
- Filename rename count: 2 (verified via Glob `**/elengenix*`).
- Directory rename count: 1 (verified via Glob `**/elengenix/**` — only top-level matches).

---

*End of Phase 2-E master rename plan.*
