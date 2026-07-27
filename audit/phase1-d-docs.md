# Phase 1-D — Documentation Inventory & README Structure Audit

**Task ID:** P1-D
**Agent:** general-purpose (P1-D)
**Scope:** `/home/z/my-project/securagentx-work/` (excludes `.git/`)
**Date:** 2026-07-27

---

## 1. Total Markdown File Count

**Total `.md` files in repo (excluding `.git/`): 19**

Source command:
```
find . -path ./.git -prune -o -name "*.md" -print | sort
```

### Full file inventory (19 files)

| # | Path | Location |
|---|------|----------|
| 1 | `README.md` | top-level |
| 2 | `AGENTS.md` | top-level |
| 3 | `AGENT_REVIEW.md` | top-level |
| 4 | `CHANGELOG.md` | top-level |
| 5 | `CLAUDE.md` | top-level |
| 6 | `CODE_OF_CONDUCT.md` | top-level |
| 7 | `CONTRIBUTING.md` | top-level |
| 8 | `FIX_NOTES.md` | top-level |
| 9 | `HANDOFF.md` | top-level |
| 10 | `MEMORY.md.example` | top-level (template, not pure `.md`) |
| 11 | `SECURITY.md` | top-level |
| 12 | `docs/TOOL_CATALOG.md` | docs/ |
| 13 | `docs/compose/plans/2026-07-02-vuln-finder-implementation.md` | docs/compose/plans/ |
| 14 | `docs/compose/specs/2026-07-02-vuln-finder-design.md` | docs/compose/specs/ |
| 15 | `examples/plugins/README.md` | examples/plugins/ |
| 16 | `knowledge/methodology.md` | knowledge/ |
| 17 | `tests/API_REFERENCE.md` | tests/ |
| 18 | `tools/api_reference.md` | tools/ |
| 19 | `.github/ISSUE_TEMPLATE/bug_report.md` | .github/ISSUE_TEMPLATE/ |
| 20 | `.github/ISSUE_TEMPLATE/feature_request.md` | .github/ISSUE_TEMPLATE/ |
| 21 | `.github/PULL_REQUEST_TEMPLATE.md` | .github/ |

> Note: The task description listed `MEMORY.md.example` alongside the `.md` files. It uses a `.example` suffix but is Markdown content. Counting it as one of the 19 markdown files in the inventory yields **19 pure `.md` + 1 `.md.example` = 20 documentation files total**. The `find -name "*.md"` glob does not match `MEMORY.md.example`, so the strict `.md` count is **19**; the documentation inventory including templates is **20**.

---

## 2. Per-File "Elengenix" Occurrence Count (case-insensitive)

Counted via `grep -ioE "elengenix" <file> | wc -l`.

| File | "elengenix" count |
|------|------------------:|
| `README.md` | **32** |
| `HANDOFF.md` | **50** |
| `docs/TOOL_CATALOG.md` | **22** |
| `CLAUDE.md` | **12** |
| `tests/API_REFERENCE.md` | **9** |
| `CONTRIBUTING.md` | **7** |
| `examples/plugins/README.md` | **6** |
| `AGENT_REVIEW.md` | **5** |
| `SECURITY.md` | **3** |
| `AGENTS.md` | **2** |
| `docs/compose/plans/2026-07-02-vuln-finder-implementation.md` | **2** |
| `tools/api_reference.md` | **2** |
| `CHANGELOG.md` | **1** |
| `MEMORY.md.example` | **1** |
| `docs/compose/specs/2026-07-02-vuln-finder-design.md` | **1** |
| `knowledge/methodology.md` | **1** |
| `CODE_OF_CONDUCT.md` | **0** |
| `FIX_NOTES.md` | **0** |
| `.github/ISSUE_TEMPLATE/bug_report.md` | **0** |
| `.github/ISSUE_TEMPLATE/feature_request.md` | **0** |
| `.github/PULL_REQUEST_TEMPLATE.md` | **0** |

**Total occurrences across all documentation: 156**

### Observations
- `HANDOFF.md` (50) is the densest — it is a coverage-push handoff document and is not user-facing. Likely a candidate for archival or removal in the rebrand.
- `README.md` (32) is the primary user-facing surface that will require the most rewrites in the README phase.
- `docs/TOOL_CATALOG.md` (22) is auto-generated from `tools/*.py` docstrings — the brand string will reappear on regeneration unless the generator is updated. Worth flagging for the code-rename phase.
- Zero-occurrence files (`CODE_OF_CONDUCT.md`, `FIX_NOTES.md`, GitHub templates) need no rebrand edits.
- `FIX_NOTES.md` actually contains "elengix" (wrong spelling) but **0 "elengenix"** — see Known Pitfalls below.

---

## 3. `docs/` Directory Tree

```
docs/
├── TOOL_CATALOG.md
└── compose/
    ├── plans/
    │   └── 2026-07-02-vuln-finder-implementation.md
    └── specs/
        └── 2026-07-02-vuln-finder-design.md
```

### Notes on docs/ contents
- `TOOL_CATALOG.md` — auto-generated catalog of 98 tool modules (header reads `# Elengenix Tool Catalog (98 modules, auto-generated)`, last updated 2026-06-07). Brand string appears in the H1 and other body text.
- `compose/plans/2026-07-02-vuln-finder-implementation.md` — implementation plan for the adaptive vuln finder; uses the compose:subagent skill convention with `- [ ]` task checkboxes.
- `compose/specs/2026-07-02-vuln-finder-design.md` — design spec (mixed Thai/English); H1 is `# Adaptive Vulnerability Finder — Design Spec`.

---

## 4. README.md Structure Analysis

### 4.1 Main Section Headings (H1, H2)

**H1 (level 1 `#`): NONE.** README.md has no top-level H1. The title block is rendered inside an HTML `<div align="center">` with an H3 (`### Autonomous AI Security Research Framework`) and an italic tagline. The product logo (`assets/elengenix.png`) carries the visual title.

**H2 (level 2 `##`) headings, in order:**

1. `## What is Elengenix?`
2. `## Quick Start`
3. `## Features`
4. `## CLI Commands`
5. `## Architecture`
6. `## Configuration`
7. `## Testing`
8. `## Project Structure`
9. `## Contributing`
10. `## License`

**H3 sub-sections (for reference):**
- Quick Start → Install, First Run, Terminal Demo
- Features → True AI Agent Architecture, Memory & Skills, Safety by Design, MCP Integration
- CLI Commands → Core, Multi-target, Shortcuts
- Configuration → MCP Servers (mcp.json), AI Providers

### 4.2 Features List (key bullet points)

Extracted verbatim from README.md lines 121–126 (the **True AI Agent Architecture** feature block) plus the MCP Integration default-server bullets (lines 172–175) and Contributing core-rules bullets (lines 331–335).

**Core feature bullets (True AI Agent Architecture section):**
- **No script chains** — AI decides every step, no locked phase ordering
- **25 built-in tools** — from port scanning to fuzzing, all described for AI consumption
- **`edit_own_tool`** — AI can create and modify its own tools at runtime
- **`create_tool`** — AI can author arbitrary Python tools on the fly
- **Cross-session Memory** — Remembers what worked (ChromaDB + Skills JSON store)
- **MCP Auto-start** — MCP server boots in background with every command

**Default MCP servers (MCP Integration section):**
- `sequential-thinking` — Structured problem-solving
- `chain-of-recursive-thoughts` — Deep recursive analysis
- `mcp-structured-thinking` — Step-by-step planning
- `memory` — Cross-session memory

**Contributing core rules bullets:**
- 4-space indentation
- Type hints everywhere
- Shell commands only behind Governance
- API keys in `.env` only
- AI agents get genuine autonomy — no forced tool ordering

### 4.3 Other Notable README Content for Rewrite Phase
- **Hero block (lines 1–17):** `<div align="center">` with `assets/elengenix.png` logo, typing-animation SVG, H3 tagline, and 5 badges (Python 3.10+, GPL-3.0, Tests 334 passing, MCP Supported, Security Governance). Badge URLs point at `github.com/moussa12345678/Elengenix`.
- **Architecture diagrams:** ASCII flow diagrams (VulnAgent cycle, MCP transport) — contain the `elengenix` command name in code blocks.
- **CLI commands listed:** `hunt`, `scan`, `vuln-hunt`, `tui`, `configure`, `doctor` (plus `bb`, `check`, `test` shortcuts marked deprecated).
- **Project Structure tree:** Mentions `Elengenix/` as the root directory name and `elengenix/` as the canonical module location.
- **License section:** GPL-3.0, with a GitHub Stars badge pointing to `moussa12345678/Elengenix`.
- **Asset references:** `assets/elengenix.png`, `assets/red-divider.svg`, `assets/typing-animation.svg`.
- **Test count claims:** README says 334 tests; CLAUDE.md says 379+; HANDOFF.md says 1060 passed — inconsistent across docs (flag for reconciliation during rewrite).

---

## 5. Top-Level Documentation File Summary

| File | Purpose | Brand present? | Notes for rewrite |
|------|---------|:--------------:|-------------------|
| `README.md` | User-facing project overview & quickstart | Yes (32) | Primary rewrite target |
| `AGENTS.md` | Working protocol for AI agents (Thai-language, MCP thinking tools rules) | Yes (2) | Brand appears in H1 only |
| `AGENT_REVIEW.md` | Internal architecture review of agent design (read-only critique) | Yes (5) | Internal doc; consider archiving |
| `CHANGELOG.md` | v1.0.0 release notes | Yes (1) | Single mention in intro line |
| `CLAUDE.md` | Guidance for Claude Code (project overview, commands, patterns) | Yes (12) | Heavy rebrand needed |
| `CODE_OF_CONDUCT.md` | Contributor Covenant v2.1 | No (0) | No edits required |
| `CONTRIBUTING.md` | Contributor guide (setup, standards, security) | Yes (7) | File tree diagram has stale filenames (e.g. `elengenix_launcher.py`, `agent_brain.py`, `orchestrator.py`) — needs sync with actual repo layout |
| `FIX_NOTES.md` | Notes on 5 test failures in `test_elengix_agent_memory.py` | No (0) | Uses wrong spelling "elengix"; internal note, candidate for removal |
| `HANDOFF.md` | Coverage-push handoff doc (156 occurrences context) | Yes (50) | Internal/temporal doc; recommend archive or delete |
| `MEMORY.md.example` | Template for AI personal memory profile | Yes (1) | Single reference in header comment |
| `SECURITY.md` | Security policy & reporting | Yes (3) | Contact `AAAAAACD@proton.me` — decide if contact changes with rebrand |

---

## 6. Known Pitfalls & Cross-File Inconsistencies

1. **Package name spelling drift** — `HANDOFF.md` explicitly warns that `elengenix` (9 chars) is correct and `elengix` (7 chars) is wrong; `FIX_NOTES.md` and `tests/test_elengix_agent_memory.py` use the wrong spelling. Any rename phase must reconcile both spellings and update `--cov=elengenix` invocations.
2. **Test count mismatch** — README says 334 tests, CLAUDE.md says 379+, HANDOFF.md says 1060 passed. Pick a canonical number for the rewrite.
3. **CONTRIBUTING.md file tree is stale** — Lists `elengenix_launcher.py`, `agent_brain.py`, `orchestrator.py`, `ui_components.py`, `bot.py`, etc. at top level. Actual repo has these under `tools/`, `core/`, `cli/`, `integrations/`. Tree needs to be regenerated from real layout.
4. **Auto-generated docs** — `docs/TOOL_CATALOG.md` is regenerated from `tools/*.py` docstrings. Brand strings will reappear unless the generator (`scripts/gen_logo.py` is not it — likely a separate script) is updated. Find the generator before rebranding this file.
5. **Mixed-language docs** — `AGENTS.md`, `docs/compose/specs/2026-07-02-vuln-finder-design.md` use Thai; rename must preserve non-English content.
6. **No H1 in README** — The rebranded README should add a proper `# SecAgentX` (or chosen name) H1 for accessibility and GitHub TOC consistency.
7. **Asset filenames contain brand** — `assets/elengenix.png`, `assets/elengenix-red.png`, `elengenix-pentagi-integration.tar.gz`, package dir `elengenix/`. These are out of scope for the docs phase but must be tracked for the asset/code-rename phases.
8. **Badge URLs** point to `github.com/moussa12345678/Elengenix` — README rewrite should update or remove these URLs depending on the new repository location.

---

## 7. Next Actions (Handoff to README Rewrite Phase)

1. **Confirm new brand name** before any edits.
2. **Rewrite README.md** — preserve H2 structure but replace all 32 brand occurrences, add H1, update badge URLs, reconcile test count, fix Project Structure tree.
3. **Update CLAUDE.md** — 12 occurrences + stale architecture overview (references `pipeline/phase_registry.py`, `pipeline/unified.py`, `core/brain.py` as canonical — README says these are removed).
4. **Update CONTRIBUTING.md** — 7 occurrences + stale file-tree.
5. **Decide fate of internal docs** — `HANDOFF.md`, `AGENT_REVIEW.md`, `FIX_NOTES.md` are temporal/internal; recommend moving to `audit/` or `archive/` rather than rebranding.
6. **Reconcile CLAUDE.md vs README.md architecture claims** — CLAUDE.md describes a 6-phase pipeline + 3-agent brain; README.md says pipeline is "fully removed" and only VulnAgent runs. Pick the truth.
7. **Defer auto-generated file rewrites** (`docs/TOOL_CATALOG.md`) until the code-rename phase updates the generator.
8. **Defer `.github/` template rewrites** — they have 0 brand mentions but should be reviewed for repo-URL updates.

---

*Report prepared by general-purpose sub-agent P1-D.*
