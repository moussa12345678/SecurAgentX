# Phase 1-C — Configuration & CI File Inventory

**Scope:** `/home/z/my-project/securagentx-work/`
**Task ID:** P1-C
**Purpose:** Inventory all configuration / CI files and count `elengenix` references (case-insensitive) to support the project rename audit.

---

## 1. Config files inventoried

| # | File | Present? |
|---|------|----------|
| 1 | `pyproject.toml` | ✅ |
| 2 | `pytest.ini` | ✅ |
| 3 | `requirements.txt` | ✅ |
| 4 | `.gitignore` | ✅ |
| 5 | `.pre-commit-config.yaml` | ✅ |
| 6 | `.mcp.json` | ✅ |
| 7 | `mcp.json.example` | ✅ |
| 8 | `config.yaml.example` | ✅ |
| 9 | `.env.example` | ✅ |
| 10 | `setup.py` | ❌ (does not exist) |
| 11 | `setup.cfg` | ❌ (does not exist) |
| 12 | `Makefile` | ❌ (does not exist) |
| 13 | `AGENTS.md` | ✅ |
| 14 | `CLAUDE.md` | ✅ |
| 15 | `MEMORY.md.example` | ✅ |

### GitHub-specific files (under `.github/`)

| # | File | Present? |
|---|------|----------|
| 16 | `.github/workflows/ci.yml` | ✅ |
| 17 | `.github/workflows/test.yml` | ✅ |
| 18 | `.github/PULL_REQUEST_TEMPLATE.md` | ✅ |
| 19 | `.github/ISSUE_TEMPLATE/bug_report.md` | ✅ |
| 20 | `.github/ISSUE_TEMPLATE/feature_request.md` | ✅ |

---

## 2. Per-file count of `elengenix` (case-insensitive)

| File | Count | Matching lines / notes |
|------|-------|------------------------|
| `pyproject.toml` | **6** | `name = "elengenix"`; `{name = "Elengenix Project"}`; `elengenix = "main:main"`; 3 URLs in `[project.urls]` |
| `pytest.ini` | 0 | — |
| `requirements.txt` | **1** | line 2: `# Elengenix - Professional Security Stack` (comment only) |
| `.gitignore` | **2** | line 2: `# Elengenix Git Ignore Configuration`; line 27: `elengenix.db` (runtime DB filename) |
| `.pre-commit-config.yaml` | 0 | — |
| `.mcp.json` | **2** | line 9 + line 13: `"/mnt/data/Elengenix"` path args for filesystem + git MCP servers |
| `mcp.json.example` | 0 | — |
| `config.yaml.example` | **1** | line 2: `# Elengenix Configuration Template (v99999)` (comment only) |
| `.env.example` | **1** | line 2: `# Elengenix Environment Variables Template` (comment only) |
| `AGENTS.md` | **2** | line 1: `# AGENTS.md — How to Work with Elengenix`; line 143: `elengenix-dev skill` |
| `CLAUDE.md` | **12** | description (line 7); CLI command examples `elengenix doctor/configure/scan/tui/bb/check/test/hack` (lines 9, 24, 60, 63, 66, 69, 72–75); `~/.elengenix/data/` path (line 209) |
| `MEMORY.md.example` | **1** | line 5: `# This file is AUTO-GENERATED and AUTO-UPDATED by Elengenix.` |
| `.github/workflows/ci.yml` | **1** | line 42: `python -m elengenix --help \|\| elengenix --help \|\| true` (boot smoke test — appears as 2 hits in raw text but counts as 1 matched line; ripgrep line-count mode = 1) |
| `.github/workflows/test.yml` | 0 | — |
| `.github/PULL_REQUEST_TEMPLATE.md` | 0 | — |
| `.github/ISSUE_TEMPLATE/feature_request.md` | 0 | — |
| `.github/ISSUE_TEMPLATE/bug_report.md` | 0 | — |

**Total `elengenix` hits across config/CI files: 31** (on 16 distinct matched lines / 30 line-occurrences)

> Note: `setup.py`, `setup.cfg`, `Makefile` do not exist in the repo, so they contribute nothing.

---

## 3. `pyproject.toml` `[project.scripts]` entry

```toml
[project.scripts]
elengenix = "main:main"
```

**Single console_script entry point:** `elengenix` → `main:main` (invokes `main()` in top-level `main.py`).

---

## 4. `pyproject.toml` `[project.urls]`

```toml
[project.urls]
Homepage = "https://github.com/moussa12345678/Elengenix"
Repository = "https://github.com/moussa12345678/Elengenix"
Issues = "https://github.com/moussa12345678/Elengenix/issues"
```

All 3 URLs point to the **moussa12345678/Elengenix** GitHub repo.

---

## 5. Other `elengenix`-referencing identifiers in `pyproject.toml`

| Field | Value | Rename-relevant? |
|-------|-------|------------------|
| `[project] name` | `elengenix` | ✅ distribution / package name |
| `[project] authors` | `{name = "Elengenix Project"}` | ✅ author label |
| `[project.scripts]` | `elengenix = "main:main"` | ✅ console_scripts entry |
| `[project.urls].Homepage` | `https://github.com/moussa12345678/Elengenix` | ✅ repo URL |
| `[project.urls].Repository` | `https://github.com/moussa12345678/Elengenix` | ✅ repo URL |
| `[project.urls].Issues` | `https://github.com/moussa12345678/Elengenix/issues` | ✅ repo URL |

---

## 6. CI workflows list and which reference `elengenix`

| Workflow | Triggers | References `elengenix`? | Detail |
|----------|----------|-------------------------|--------|
| `.github/workflows/ci.yml` | push / PR to `main` | ✅ YES | Matrix build (Py 3.11 / 3.12 / 3.13). Step "Boot smoke test" runs `python -m elengenix --help \|\| elengenix --help \|\| true` — invokes both the module name and the installed console_script. |
| `.github/workflows/test.yml` | push / PR to `main` | ❌ NO | Single-job Py 3.12 test runner. Ignores several integration-heavy tests; does not invoke `elengenix` by name. |

**Other `.github/` files (not workflows):**
- `.github/PULL_REQUEST_TEMPLATE.md` — no `elengenix` refs.
- `.github/ISSUE_TEMPLATE/bug_report.md` — no `elengenix` refs (references `python3 main.py` instead).
- `.github/ISSUE_TEMPLATE/feature_request.md` — no `elengenix` refs.

---

## 7. Highlights for the rename effort (next phases)

Items that MUST be touched when renaming away from "elengenix":

1. **`pyproject.toml`** — distribution name, console_script, author label, 3 URLs (6 hits).
2. **`.mcp.json`** — 2 hard-coded absolute paths `/mnt/data/Elengenix` (filesystem + git MCP servers). These are runtime paths; decide whether to keep or rename.
3. **`.gitignore`** — runtime DB filename `elengenix.db` (line 27) plus header comment.
4. **`.github/workflows/ci.yml`** — smoke-test step calls `python -m elengenix` and `elengenix` CLI; must match the new package name and console_script.
5. **`CLAUDE.md`** — 12 hits (CLI command examples + `~/.elengenix/data/` user-data dir path).
6. **`AGENTS.md`** — header + reference to `elengenix-dev skill`.
7. **Comment-only cosmetic hits** in `requirements.txt`, `config.yaml.example`, `.env.example`, `MEMORY.md.example` (1 each).
8. **No `setup.py` / `setup.cfg` / `Makefile`** to migrate — `pyproject.toml` is the sole build config.

Items that need **no change**: `pytest.ini`, `.pre-commit-config.yaml`, `mcp.json.example`, all three template files under `.github/` (PR template + 2 issue templates), and `.github/workflows/test.yml`.

---

*Generated by P1-C audit agent.*
