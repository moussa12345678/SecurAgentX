# P4-C — Ruthless egg-info + Binary Audit

**Task ID:** P4-C
**Agent:** general-purpose (P4-C)
**Scope:** `securagentx.egg-info/` directory + ALL binary/generated files in `/home/z/my-project/securagentx-work/`
**Target string:** `<OLD-ORG>` / `<old-org>` (any case, any variant) + broader `[<OLD-ORG>]` stem
**Date:** 2026-07-28

---

## 1. egg-info/ Directory Audit

Directory listing (`ls -la securagentx.egg-info/`):

| File | Size | Notes |
|------|------|-------|
| PKG-INFO | 21749 B | package metadata |
| SOURCES.txt | 13685 B | source manifest |
| dependency_links.txt | 1 B | empty |
| entry_points.txt | 42 B | console scripts |
| requires.txt | 604 B | runtime deps |
| top_level.txt | 123 B | top-level packages |

**Total files in egg-info/:** 6

### 1a. `<old-org>` (case-insensitive) in egg-info/
```
grep -rIn -i "<old-org>" securagentx.egg-info/
```
→ **0 files matched, 0 occurrences.** (ripgrep `--ignore-case` via Grep tool confirmed)

### 1b. `[<OLD-ORG>]` broader stem in egg-info/
```
grep -rIn -E "[<OLD-ORG>]" securagentx.egg-info/
```
→ **0 files matched, 0 occurrences.** (Grep tool confirmed)

**egg-info verdict: CLEAN** — no <OLD-ORG> residue in any of the 6 generated metadata files.

---

## 2. Repo-wide `<old-org>` scan (excluding .git, audit, ,cover, *.tar.gz)

```
grep -rIl -i "<old-org>" /home/z/my-project/securagentx-work/ \
    --exclude-dir=.git --exclude-dir=audit --exclude="*,cover" --exclude="*.tar.gz"
```
→ **0 files matched.** (Grep tool over full repo path, no excludes needed because it returned no matches anywhere)

### 2a. Broader `[<OLD-ORG>]` stem across whole repo
```
grep -rIl -E "[<OLD-ORG>]" /home/z/my-project/securagentx-work/
```
→ **0 files matched.** Includes a recursive ripgrep over the entire work tree with no path exclusions; zero hits.

**Source-tree verdict: CLEAN** — the live working tree (Python source, tests, configs, docs, prompts, mcp/, cli/, agents/, securagentx/, tools/, integrations/, tui/, etc.) contains zero <OLD-ORG> references.

---

## 3. Binary / generated file inventory

```
find /home/z/my-project/securagentx-work/ -path ./.git -prune -o -type f -print \
    | xargs file | grep -iE "binary|image|compressed"
```

**Total binary/image/compressed files in repo: 9**

| # | Path | file(1) classification |
|---|------|------------------------|
| 1 | `assets/securagentx.png` | PNG image data, 770×260, 8-bit RGBA |
| 2 | `assets/securagentx-red.png` | PNG image data, 770×260, 8-bit RGBA |
| 3 | `assets/0dgcM3RU_400x400.jpg` | JPEG image data, JFIF, 400×400 |
| 4 | `assets/typing-animation.svg` | SVG Scalable Vector Graphics (ASCII text) |
| 5 | `assets/color-cycle.svg` | SVG Scalable Vector Graphics (ASCII text) |
| 6 | `assets/logo-animated.svg` | SVG Scalable Vector Graphics (Unicode text) |
| 7 | `assets/red-divider.svg` | SVG Scalable Vector Graphics (ASCII text) |
| 8 | `securagentx/docker/image_chooser.py` | *(false-positive — Python script, text; filename contains "image")* |
| 9 | `elengenix-pentagi-integration.tar.gz` | gzip compressed data, original size ~3.5 MB |

### 3a. Binary-content scan for `<old-org>` (via `strings -a | grep -ic`)

Each binary asset was scanned with `strings -a` then case-insensitive grep:

| File | `<old-org>` hits | `[<OLD-ORG>]` hits |
|------|-----------------|-------------------|
| `assets/securagentx.png` | 0 | 0 |
| `assets/securagentx-red.png` | 0 | 0 |
| `assets/0dgcM3RU_400x400.jpg` | 0 | 0 |
| `assets/typing-animation.svg` | 0 | 0 |
| `assets/color-cycle.svg` | 0 | 0 |
| `assets/logo-animated.svg` | 0 | 0 |
| `assets/red-divider.svg` | 0 | 0 |
| `elengenix-pentagi-integration.tar.gz` | **6** | **6** |

**Static-asset binaries are clean.** The tarball is NOT clean — see §5.

---

## 4. Tarball top-level contents (filenames only, no extraction)

```
tar tzf elengenix-pentagi-integration.tar.gz | head -30
```
```
elengenix/
elengenix/tools/
elengenix/tools/__init__.py
elengenix/types.py
elengenix/agents/
elengenix/agents/adviser.py
elengenix/agents/assistant.py
elengenix/agents/installer.py
elengenix/agents/reporter.py
elengenix/agents/primary_agent.py
elengenix/agents/__init__.py
elengenix/agents/searcher.py
elengenix/agents/generator.py
elengenix/agents/pentester.py
elengenix/agents/coder.py
elengenix/agents/refiner.py
elengenix/agents/toolcall_fixer.py
elengenix/agents/reflector.py
elengenix/agents/memorist.py
elengenix/agents/enricher.py
elengenix/agents/summarizer.py
elengenix/agents/base.py
elengenix/paths.py
elengenix/controllers/
elengenix/constitution_engine.py
elengenix/search_providers/
elengenix/search_providers/duckduckgo.py
elengenix/search_providers/registry.py
elengenix/search_providers/searxng.py
elengenix/search_providers/__init__.py
```

**Total tarball entries: 174** (all paths, including directory markers).

### 4a. Tarball *filenames* matching `<old-org>` / `[<OLD-ORG>]`
```
tar tzf elengenix-pentagi-integration.tar.gz | grep -i "<old-org>"   → 0
tar tzf elengenix-pentagi-integration.tar.gz | grep -iE "[<OLD-ORG>]" → 0
```
**Total tarball entries (filenames) containing <old-org>: 0.**

### 4b. Tarball *content* scan (binary-aware `strings` stream)

```
tar xzf elengenix-pentagi-integration.tar.gz -O | strings -a | grep -icE "<old-org>"  → 6
```

Six occurrences of `<OLD-ORG>` survive **inside the tarball's file contents** even though no tarball *filename* contains it. To localise the hits, the tarball was extracted to a throwaway `/tmp/p4c-tar-check/` scratch dir (NOT into the repo) and re-scanned with the Grep tool:

| File inside tarball | `<old-org>` occurrences | Context |
|---------------------|------------------------|---------|
| `elengenix/pyproject.toml` | 3 | L90 `Homepage = "https://github.com/<OLD-ORG>/Elengenix"`; L91 `Repository = "https://github.com/<OLD-ORG>/Elengenix"`; L92 `Issues = "https://github.com/<OLD-ORG>/Elengenix/issues"` |
| `elengenix/README.md` | 3 | L13 tests badge → `github.com/<OLD-ORG>/Elengenix/actions`; L15 security badge → `github.com/<OLD-ORG>/Elengenix`; L349 stars badge → `github.com/<OLD-ORG>/Elengenix` |
| **Total** | **6** | all are GitHub URLs in the `<OLD-ORG>/Elengenix` org path |

The scratch dir was deleted (`rm -rf /tmp/p4c-tar-check`) after analysis; **nothing was written back into the repo**.

### 4c. Live-repo cross-check (confirm the working tree does NOT have the same leak)

```
grep -in "<old-org>" securagentx-work/pyproject.toml   → No matches found
grep -in "<old-org>" securagentx-work/README.md        → No matches found
grep -in "github.com/[A-Za-z0-9_]+/Elengenix" securagentx-work/pyproject.toml → No matches found
```
The live `securagentx-work/pyproject.toml` and `README.md` were correctly renamed to the `moussa12345678/SecurAgentX` (or equivalent) identity. **Only the stale tarball artifact still embeds the old `<OLD-ORG>/Elengenix` GitHub URLs.**

---

## 5. Verdict

| Metric | Value |
|--------|-------|
| Files in `securagentx.egg-info/` with `<old-org>` matches | **0** |
| Files in `securagentx.egg-info/` with `[<OLD-ORG>]` matches | **0** |
| Files in repo (excl. .git/audit/cover/tarball) with `<old-org>` | **0** |
| Files in repo with `[<OLD-ORG>]` stem | **0** |
| **Total binary/image/compressed files in repo** | **9** (7 real binaries + 1 false-positive text file matched on filename + 1 tarball) |
| Binary asset files containing `<old-org>` (strings scan) | **0** |
| **Total tarball entries (filenames) containing `<old-org>`** | **0** |
| **Total tarball file-contents occurrences of `<old-org>`** | **6** (across 2 files: `pyproject.toml` ×3, `README.md` ×3) |

### VERDICT: ❌ FAIL

The live source tree, the `securagentx.egg-info/` directory, and all static-asset binaries (PNG/JPG/SVG) are **clean** — zero <OLD-ORG> residue.

**However**, the binary/generated artifact `elengenix-pentagi-integration.tar.gz` (3.5 MB gzip archive at the repo root) **still embeds 6 occurrences of `<OLD-ORG>`** inside its contents — all in the form of GitHub URLs `https://github.com/<OLD-ORG>/Elengenix[...]` spread across `elengenix/pyproject.toml` (×3) and `elengenix/README.md` (×3). No tarball *filename* contains the string, so a filename-only audit would miss this; only a content-level `strings` scan on the archive catches it.

---

## 6. Required remediation

The tarball `elengenix-pentagi-integration.tar.gz` is a **stale pre-rebrand snapshot** of the integration package. Three options, in descending order of safety:

1. **Delete the tarball entirely** if it is no longer needed (recommended — it predates the rename and its embedded `<OLD-ORG>/Elengenix` URLs are dead links anyway).
2. **Regenerate the tarball** from the current renamed `securagentx/` tree so it carries the new `moussa12345678/SecurAgentX` identity, then replace the stale archive in place.
3. **Edit-in-place** (extract → sed-replace `<OLD-ORG>`→`moussa12345678` and `Elengenix`→`SecurAgentX` → re-tar -czf) — only if the tarball must preserve its current file list verbatim.

Until one of these is performed, the repo ships a binary artifact that leaks the prior `<OLD-ORG>` GitHub-org identity.

---

## 7. Defensive notes

- The `securagentx/docker/image_chooser.py` line in the `file | grep` output is a **false positive**: `file(1)` reports it as "Python script, Unicode text", but the grep matched the substring "image" in the *filename*, not in the file-type description. It is plain UTF-8 text and contains no `<old-org>`.
- The 4 SVG files are XML text (ASCII/Unicode) but are classified as "image" by `file(1)`; all 4 were string-scanned and are clean.
- The PNG/JPG files were string-scanned (`strings -a`) for embedded metadata/EXIF; none contain the target string.
- The `securagentx.egg-info/` directory is regenerated by `pip install -e .` / `python -m build`; since the live `pyproject.toml` is clean, any future regeneration will produce clean egg-info metadata. The current on-disk egg-info (timestamped 2026-07-27 23:39) was generated post-rename and is verified clean.
