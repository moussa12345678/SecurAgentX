## 3. CLI Commands

SecurAgentX ships a single `securagentx` console script (entry point `main:main` in `pyproject.toml`) plus an equivalent `python -m securagentx` module invocation that imports `main.py` via `securagentx/__main__.py`. Both paths boot the same CLI: banner → config bootstrap (`_ensure_config_files()` copies `mcp.json.example`, `.env.example`, `config.yaml.example` into `~/.securagentx/` on first run) → MCP auto-start → command dispatch.

```bash
# Installed entry point (recommended)
securagentx hunt example.com

# Module invocation (editable install / dev)
python -m securagentx hunt example.com

# Direct script (clone root)
python3 main.py hunt example.com
```

### 3.1 Global Options

Every command accepts these flags. Some are only meaningful for specific commands (called out below); unrecognized flags are passed through `argparse.parse_known_args()` so plugins can extend the parser.

| Flag | Type | Default | Description |
|:-----|:-----|:--------|:------------|
| `--rate-limit` | int | `5` | Max requests per second for HTTP-driven tools. |
| `--framework` | str | `generic` | Target framework for PoC generation (`spring-boot`, `django`, …). |
| `--version` | str | `""` | Target software version for PoC generation. |
| `--mode` | `{strict,ask,auto}` | `ask` | Governance mode for `autonomous`/`hunt` — `strict` asks on every action, `ask` only on dangerous, `auto` approves all. |
| `--smart-scan` | flag | off | Enable file-relationship analysis & finding correlation. Sets `SECURAGENTX_SMART_SCAN=1`. |
| `--quiet`, `-q` | flag | off | Suppress phase-by-phase output; show summary + report path only. Sets `SECURAGENTX_QUIET=1`. |
| `--format` | str | `html` | Output format for `scan-report` (`html`/`md`/`sarif`/`json`/`txt`/`all`). |
| `--output` | path | derived | Output path for `scan-report` / `compliance`. |
| `--host` | str | `0.0.0.0` | Bind address for `api` server. |
| `--port` | int | `8443` | Port for `api` server (default `8080` for `mcp http`). |
| `--yes`, `-y` | flag | off | Auto-yes to prompts (`update --apply`). |
| `--no-auto-report` | flag | off | Skip auto-generated HTML report after scan. |
| `--check` | flag | off | `update` — check for updates without applying. |
| `--apply` | flag | off | `update` — apply update if available. |
| `--force` | flag | off | Force refresh (skip cache). |
| `--verified` | flag | off | `marketplace search` — show only verified plugins. |
| `--upgrade` | flag | off | `marketplace install` — force-reinstall plugin. |
| `--phase` | `{recon,waf,fuzz,bola,learn,coverage}` | — | Run only a specific scan phase (redirected to VulnAgent; AI selects tools). |
| `--interactive` | `{bola,waf,recon}` | — | Run interactive mode (redirected to VulnAgent). |

### 3.2 Command Reference

Commands are dispatched in `main.py:main()` via an `if/elif` chain over `args.command`, with a final fallback to `commands.registry.CommandRegistry` for any command registered via the `@command(...)` decorator (used by `commands/system.py` and any plugin-discovered command). Unknown commands trigger a fuzzy `CommandSuggester` "did you mean?" prompt.

#### Core AI Agent — True VulnAgent

| Command | Description | Example |
|:--------|:------------|:--------|
| `hunt <target>` | Autonomous AI vulnerability hunt — VulnAgent reasons over 25 tools, pivots freely, writes new tools when needed. Report saved to `~/.securagentx/reports/hunt_<target>_<ts>.md`. | `securagentx hunt example.com` |
| `scan <target>` | Alias of `hunt` routed through `commands/scan.py:handle_scan` — VulnAgent-driven scan that ignores legacy phase locking. | `securagentx scan api.example.com --smart-scan` |
| `vuln-hunt <target>` | Full autonomous vulnerability hunt (same VulnAgent path, longer mission prompt). Triggered automatically when you pass a bare target. | `securagentx vuln-hunt https://target.tld` |
| `autonomous <target> [--mode {strict\|ask\|auto}]` | Fully autonomous mode — AI controls tool selection, dep installation, and tool creation. `auto` mode bypasses all governance gates. | `securagentx autonomous https://target.tld --mode auto` |
| `hunt "t1, t2"` | Multi-target hunt — comma-separated list dispatched sequentially to VulnAgent. | `securagentx hunt "example.com, api.example.com"` |

#### Interface Modes

| Command | Description | Example |
|:--------|:------------|:--------|
| `tui` (also `cli`, `cli-textual`, `clitest`, `universal`) | Launch the Textual TUI chat interface (`cli/textual.py`). Default when no command/target given. | `securagentx tui` |
| `cli-legacy` | Rich-based interactive REPL (`cli/interactive.py`) — pre-Textual UI. | `securagentx cli-legacy` |
| `menu` | Interactive wizard menu (`tui/main_menu.py`) — pick a module from a list. | `securagentx menu` |
| `arsenal` | Tools menu (`cli/tools_menu.py`) — browse the 100+ tool catalog interactively. | `securagentx arsenal` |
| `gateway` | Start the Telegram bot gateway (`bot.py`) for remote-control via Telegram. | `securagentx gateway` |

#### Setup & Maintenance

| Command | Description | Example |
|:--------|:------------|:--------|
| `doctor` | System health check (`tools/doctor.py:check_health`) — verifies Python, dependencies, AI provider keys, MCP config, write access to `~/.securagentx/`. | `securagentx doctor` |
| `configure` | Interactive setup wizard (`tools/config_wizard.py`) — choose AI provider, paste API key, pick default model. | `securagentx configure` |
| `welcome` | First-run welcome wizard (`tools/welcome_wizard.py`) — onboarding flow. | `securagentx welcome` |
| `update [--check\|--apply\|--force] [--yes]` | Check or apply SecurAgentX self-update from GitHub releases (`tools/updater.py:Updater`). | `securagentx update --apply --yes` |
| `mcp [http\|stdio]` | Start the MCP server in foreground (`mcp/server.py:MCPServer`). Default = stdio; `http` listens on `--rate-limit` or `8080`. | `securagentx mcp http` |
| `cve-update` | Fetch latest 30 days of CVEs from NVD into the local CVE database (`tools/cve_database.py`). | `securagentx cve-update` |
| `prefetch` | Pre-download the ChromaDB embedding model (~79 MB) and tiktoken encoding so the first hunt isn't slow. | `securagentx prefetch` |
| `list-tools` | Print the full 100+ tool catalog grouped by category (recon, fuzz, exploit, reporting, ai, waf, telegram, infra, utils). | `securagentx list-tools` |
| `examples` | Print common usage patterns (`_cmd_examples` in `main.py`). | `securagentx examples` |
| `help` | Print help with contextual suggestions drawn from command history (`tools/auto_detector.py:CommandSimplifier`). | `securagentx help` |

#### Scanning & Vulnerability Classes

| Command | Description | Example |
|:--------|:------------|:--------|
| `bola <url>` | BOLA/IDOR differential harness (`tools/bola_harness.py:BOLAHarness`) — prompts for Account A & Account B headers, runs common IDOR checks + seeded endpoint checks. | `securagentx bola https://api.target.tld` |
| `waf <url>` | WAF detection & evasion testing (`tools/waf_evasion.py:WAFEvasionEngine`) — detect WAF, generate & test up to 12 mutations, report best bypass. | `securagentx waf https://target.tld/search` |
| `recon <domain>` | Smart reconnaissance (`tools/smart_recon.py:SmartReconEngine`) — subdomains, IP resolution, service fingerprinting, asset correlation. | `securagentx recon example.com --rate-limit 10` |
| `evasion` | EDR/AV evasion payload generator (`tools/edr_evasion.py:EDREvasionEngine`) — list techniques, generate payloads, plan red-team attacks. Authorized use only. | `securagentx evasion` |
| `sast <path>` | Static Application Security Testing (`tools/sast_engine.py:SASTEngine`) + multimodal code analysis on Python/JS/TS/Java/Go/Rb/PHP files. | `securagentx sast ./src` |
| `cloud <path>` | Cloud / IaC security review (`tools/cloud_scanner.py:CloudScanner`) for Terraform, YAML, JSON. | `securagentx cloud ./terraform` |
| `mobile <target>` | Mobile API analyzer (`tools/mobile_api_tester.py:MobileAPITester`) — accepts URL or Burp export file. | `securagentx mobile https://api.target.tld` |
| `soc <logfile>` | SOC log analyzer (`tools/soc_analyzer.py:SOCAnalyzer`) — detect threats in SIEM exports or raw logs. | `securagentx soc /var/log/auth.log` |
| `compliance <standard>` | Compliance assessment (`tools/compliance_engine.py:ComplianceEngine`) against PCI DSS, SOC2, ISO 27001, OWASP. Aliases: `audit`, `pci`, `soc`. | `securagentx compliance pci_dss` |

#### Enterprise & API

| Command | Description | Example |
|:--------|:------------|:--------|
| `api [--host 0.0.0.0] [--port 8443]` | Launch the Enterprise REST API server (`tools/api_server.py:run_server`) — web dashboard + OpenAPI docs at `/docs` + ReDoc at `/redoc`. | `securagentx api --port 9000` |
| `dashboard` | Launch the TUI security monitoring dashboard (`tools/tui_dashboard.py:run_dashboard`); falls back to minimal mode on TTY failure. | `securagentx dashboard example.com` |
| `ml-filter <findings.json>` | ML-powered false-positive filter (`tools/ml_filter.py`) — Bayesian scoring + signal analysis. Aliases: `ml`, `filter`. | `securagentx ml-filter findings.json --output filtered.json` |

#### Research, PoC & Reports

| Command | Description | Example |
|:--------|:------------|:--------|
| `research <cve-id\|vuln-type>` | Vulnerability research (`tools/vuln_researcher.py:VulnerabilityResearcher`) — for CVE-IDs: fetch CVSS, description, PoCs; for vuln types: print exploitation guide + generate PoC. | `securagentx research CVE-2024-21626` |
| `poc <vuln-type> [--framework] [--version]` | Generate custom PoC template for a vulnerability type. | `securagentx poc sqli --framework django --version 4.2` |
| `report <findings.json>` | Professional PDF/HTML report generator (`tools/pdf_report_generator.py:PDFReportGenerator`) — prompts for title/author/target metadata. | `securagentx report reports/example/findings.json` |
| `scan-report <findings.json> [--format] [--output]` | Apple-level HTML/MD/SARIF/JSON/TXT report from a findings JSON (`tools/report_gen.py:export_report`). `--format all` emits every format. | `securagentx scan-report findings.json --format all` |

#### Intelligence, Mission & History

| Command | Description | Example |
|:--------|:------------|:--------|
| `programs`, `intel`, `bounty` `[api\|public\|top]` | Bug-bounty program discovery (`tools/bounty_intelligence.py:BountyIntelligence`) — `api` uses `HACKERONE_API_KEY`, `public` scrapes, `top` prints single best pick. | `securagentx bounty top` |
| `mission <target> [--pause-after H]` | Start an autonomous scanning mission (`tools/smart_scanner.py:SmartScanner`) that auto-pauses after N hours without findings. | `securagentx mission target.com --pause-after 6` |
| `pause <mission_id>` | Pause a running mission. | `securagentx pause mission_20260529_001` |
| `resume <mission_id>` | Resume a paused mission. | `securagentx resume mission_20260529_001` |
| `history [list\|stats\|search\|suggest]` | Command history management (`tools/history_manager.py`) — `list` shows recent, `stats` shows favorites, `search` filters, `suggest` predicts next. | `securagentx history stats` |
| `memory` | AI memory system console (`tools/vector_memory.py`) — search memories, list known targets, clear target memory. | `securagentx memory` |

#### Profiles & Shortcuts

| Command | Description | Example |
|:--------|:------------|:--------|
| `profile [list\|create\|delete]` | Profile management (`tools/profile_manager.py:ProfileManager`) — list, clone+edit, or delete named scan profiles. | `securagentx profile create` |
| `quick <target>` | Profile shortcut — fast reconnaissance-biased scan. | `securagentx quick example.com` |
| `deep <target>` | Profile shortcut — exhaustive multi-stage scan. | `securagentx deep example.com` |
| `bounty <target>` | Profile shortcut — bounty-mode scan (rate-limited, stealth-biased). | `securagentx bounty example.com` |
| `stealth <target>` | Profile shortcut — low-and-slow evasion-biased scan. | `securagentx stealth example.com` |
| `web <target>` | Profile shortcut — web-application-focused scan. | `securagentx web https://target.tld` |

#### Plugins & Marketplace

| Command | Description | Example |
|:--------|:------------|:--------|
| `marketplace [search\|install\|uninstall\|list] [name]` | Plugin marketplace (`tools/marketplace.py:Marketplace`) — search remote registry, install/uninstall plugins, list installed. | `securagentx marketplace search sqli --verified` |
| `plugins [list\|info\|reload] [name]` | Manage loaded plugins (`tools/ecosystem.py`) — list with state, inspect manifest, hot-reload. | `securagentx plugins info ollama_local` |

#### Deprecated Aliases (still routed)

| Alias | Expands to | Note |
|:------|:-----------|:-----|
| `bb` | `scan --phase bola` | Redirects to VulnAgent BOLA-aware mission. |
| `check` | `scan --phase recon` | Redirects to VulnAgent recon mission. |
| `test` | `scan --phase waf` | Redirects to VulnAgent WAF mission. |
| `red` | `evasion` | Red-team payload generator. |
| `hack` | `hunt` | Crowd-pleaser alias. |
| `pdf` | `report` | Back-compat for report generation. |
| `<bare-target>` | `vuln-hunt <bare-target>` | Anything not a known command is treated as a target. |

### 3.3 Example Sessions

```bash
# First-time setup
securagentx doctor          # verify dependencies + paths
securagentx configure       # pick AI provider, paste API key
securagentx prefetch        # pre-download embedding model (~79 MB)

# Single-target hunt — autonomous AI agent
securagentx hunt example.com

# Quiet mode + smart scan + HTML report
securagentx scan example.com --quiet --smart-scan

# Targeted testing through the AI agent
securagentx bola https://api.target.tld
securagentx waf https://target.tld/search
securagentx recon example.com --rate-limit 10

# Code & cloud review
securagentx sast ./src
securagentx cloud ./terraform

# Generate multi-format report from saved findings
securagentx scan-report reports/example/findings.json --format all

# Bug-bounty workflow
securagentx bounty top
securagentx mission target.com --pause-after 6
securagentx resume mission_20260529_001
securagentx history stats

# Plugin ecosystem
securagentx marketplace search sqli --verified
securagentx marketplace install sqli-helper
securagentx plugins list
securagentx plugins info sqli-helper
```

### 3.4 Exit Codes

| Code | Meaning |
|:----:|:--------|
| `0` | Success. |
| `1` | Generic error (invalid target, scope violation, scan failure). |
| `130` | `Ctrl+C` interrupt (`KeyboardInterrupt` → `sys.exit(0)` after cleanup). |

<img src="assets/red-divider.svg" width="100%">

## 4. Architecture

SecurAgentX is built around a **true autonomous AI agent** — not a script chain. Every scan path (`hunt`, `scan`, `vuln-hunt`, `autonomous`) delegates to `VulnAgent`, a free-will agent that **reasons** about the target, **selects** tools from a 25-tool catalog, **pivots** when paths fail, and **authors new tools** at runtime when the existing set is insufficient. The legacy phase pipeline (`pipeline/phase_registry`, `pipeline/unified`, `core/brain.py`) has been fully removed.

### 4.1 High-Level Data Flow

```text
                       ┌──────────────────────────────────────┐
                       │  CLI Entry Point                     │
                       │  main.py / python -m securagentx     │
                       │  ├─ _ensure_config_files()           │
                       │  ├─ show_banner()                    │
                       │  └─ start_mcp_if_enabled() (daemon)  │
                       └─────────────────┬────────────────────┘
                                         │
                  ┌──────────────────────┴───────────────────────┐
                  ▼                                              ▼
       ┌───────────────────────┐                    ┌─────────────────────────┐
       │  VulnAgent            │  ←── reasons ────  │  MCP Server (background)│
       │  (securagentx/agent/) │                    │  mcp/server.py          │
       │                       │                    │  ├─ stdio transport     │
       │  AVAILABLE_TOOLS (25) │                    │  ├─ HTTP transport      │
       │  ├─ port_scan         │                    │  └─ 25 dynamic tools    │
       │  ├─ web_recon         │                    │     registered from     │
       │  ├─ vuln_scan         │                    │     AVAILABLE_TOOLS     │
       │  ├─ search_cve        │                    └─────────────┬───────────┘
       │  ├─ analyze_target    │                                  │
       │  ├─ web_search        │  ─── calls ───►  External MCP servers (npx)
       │  ├─ web_extract       │                    (sequential-thinking, memory,
       │  ├─ read/write/edit   │                     chain-of-recursive-thoughts, …)
       │  ├─ run_command       │
       │  ├─ run_python        │
       │  ├─ analyze_security  │
       │  ├─ delegate          │  ─── spawns ──►  Sub-agents (securagentx/agents/)
       │  ├─ create_tool       │  ─── self ───►   New Python tool, hot-registered
       │  ├─ edit_own_tool     │  ─── self ───►   Patched existing dynamic tool
       │  ├─ save_memory       │  ───────┐
       │  ├─ recall_memory     │  ◄──────┤
       │  ├─ list_memories     │         │
       │  ├─ forget_memory     │         │   ┌──────────────────────────────┐
       │  ├─ create_skill      │  ───────┼──►│ AgentMemory                  │
       │  ├─ view_skill        │  ◄──────┤   │ securagentx/agent/memory.py  │
       │  ├─ list_skills       │         │   │ ├─ VectorMemory (ChromaDB)   │
       │  └─ delete_skill      │         │   │ │   working / episodic /     │
       └───────────┬───────────┘         │   │ │   semantic / constitutional│
                   │                     │   │ ├─ JSON memory store         │
                   │                     │   │ │   ~/.securagentx/data/     │
                   │                     │   │ │   memory.json              │
                   │                     │   │ └─ SkillStore (skills.json)  │
                   │                     │   └──────────────────────────────┘
                   ▼                     │
       ┌───────────────────────┐         │   ┌──────────────────────────────┐
       │  GovernanceGate       │         │   │ KnowledgeGraph               │
       │  securagentx/         │         └──►│ securagentx/knowledge_graph/ │
       │  governance.py        │             │ ├─ graph.py (NetworkX+SQLite)│
       │  ├─ SAFE → run        │  ─── extracts ──► │ ├─ extractor.py        │
       │  ├─ PRIVILEGED → ask  │             │ │   (IPs/domains/CVEs/creds)│
       │  └─ DESTRUCTIVE → pop │             │ ├─ integration.py (hooks)   │
       └───────────┬───────────┘             │ ├─ community.py (Louvain)   │
                   │                         │ └─ 7 PentAGI search modes    │
                   ▼                         └──────────────────────────────┘
       ┌───────────────────────┐
       │  Constitution Engine  │  ←── reviews every action ──┐
       │  securagentx/         │                             │
       │  constitution.py +    │                             │
       │  constitution_engine  │   Constitutional Oath taken │
       └───────────┬───────────┘   at mission start; every   │
                   │               action scored for harm,   │
                   ▼               scope, proportionality    │
       ┌───────────────────────┐                             │
       │  VulnReport           │  ◄── findings + AI analysis │
       │  securagentx/agent/   │      saved to               │
       │  report.py            │      ~/.securagentx/reports/│
       └───────────────────────┘                             │
                                                           │
                          ▲ feedback loop ─────────────────┘
                          │  every step writes memory + KG episode;
                          │  Constitution reviews next action
```

### 4.2 The CLI Entry & Boot Sequence

`main.py:main()` is the single entry point. Both `securagentx` (console script in `pyproject.toml`) and `python -m securagentx` (via `securagentx/__main__.py`) call it. The boot sequence is:

1. **`ensure_path_priorities()`** — prepend `~/Downloads/go-tools/bin`, `~/go/bin`, `~/.local/bin` to `PATH` so user-installed Go tools (ffuf, nuclei, subfinder) win over system binaries.
2. **`show_banner()`** — Rich-rendered banner from `cli/ui_components.py`.
3. **`start_mcp_if_enabled()`** (`commands/mcp_runner.py`) — idempotent daemon thread that boots the MCP server in the background if `mcp.json` lists enabled servers. Failures are swallowed (`MCP is optional — don't block startup`).
4. **`_ensure_config_files()`** — copy `mcp.json.example`, `.env.example`, `config.yaml.example` into `~/.securagentx/` on first run.
5. **Argparse + dispatch** — `argparse.ArgumentParser(add_help=False)` parses only known args; unknown flags pass through to plugin handlers. Bare targets (`securagentx example.com`) auto-route to `vuln-hunt`.

### 4.3 The AI Brain — `VulnAgent` and the True Agentic Loop

The agent core lives in `securagentx/agent/vuln_agent.py:VulnAgent`. It exposes 25 tools through the `AVAILABLE_TOOLS` list (17 builtins + 4 memory/skill + `create_tool` + `edit_own_tool` + `delegate` + `analyze_security`), and runs an open-ended **REASON → TOOL SELECT → EXECUTE → ADAPT** loop with no locked phases.

Two parallel reasoning loops ship in the codebase:

| Loop | Module | Use |
|:-----|:-------|:----|
| `VulnAgent.hunt()` | `securagentx/agent/vuln_agent.py` | Default hunt/scan/vuln-hunt path — prompt-driven, MCP-aware, 25 tools. |
| `TrueAgenticLoop.run_mission()` | `securagentx/loop.py` | PentAGI-style sovereign loop with Constitutional AI gate at every step. Used by `autonomous` and mission flows. |

`TrueAgenticLoop` (in `securagentx/loop.py`) implements the cognitive cycle:

1. **Constitutional Oath** — the agent swears to uphold scope, do no harm, and be accountable before any tool runs. The oath itself is stored in constitutional memory.
2. **Perception** — `PerceptionModule.perceive()` builds situation awareness: target status, findings summary, coverage gaps, threat landscape, resource status.
3. **Reasoning** — `ReasoningEngine.reason()` selects one of six strategies (`deductive`, `inductive`, `abductive`, `analogical`, `causal`, `counterfactual`) and produces a `ReasoningResult` with premise, conclusion, confidence, alternative hypotheses.
4. **Decision** — `DecisionEngine.decide()` picks an `AIAction` from the active `AttackPlan`.
5. **Constitutional Check** — `ConstitutionalAIEngine.review_action()` scores the action for harm, scope-violation, and proportionality. If `requires_human_review` is true, the loop pauses and asks the user.
6. **Execution** — `GovernanceGate.gate()` enforces SAFE / PRIVILEGED / DESTRUCTIVE classification. SAFE runs immediately; PRIVILEGED prompts; DESTRUCTIVE pops a confirmation dialog.
7. **Reflection & Learning** — every action+result is written to memory (`CognitiveMemoryManager.remember()`) and ingested into the knowledge graph as an `Episode`.
8. **Replanning Check** — if confidence drops below `replan_threshold` (default `0.3`) or 3 consecutive failures occur, `PlanningEngine.replan()` generates a recovery plan.

The brain's planning layer (`PlanningEngine` in `securagentx/brain.py`) generates a structured `AttackPlan` with named `PlanPhase` objects — each with objective, tool list, risk level, and success criteria. Crucially, the **plan is advisory, not prescriptive**: VulnAgent can skip phases, run them out of order, or invent new ones via `create_tool`.

### 4.4 Multi-Agent Orchestration — `securagentx/agents/`

For complex missions, VulnAgent's `delegate` tool spawns sub-agents from the `securagentx/agents/` package — a 15-role hierarchy ported from PentAGI's Go implementation:

| Agent | Role |
|:------|:-----|
| `PrimaryAgent` | Root orchestrator — delegates to 6 specialists. |
| `Searcher` | Information gathering (CVEs, docs, prior art). |
| `Pentester` | Hands-on security testing. |
| `Coder` | Writes exploits, scripts, custom tools. |
| `Installer` | Environment setup, dependency installation. |
| `Memorist` | Vector + KG retrieval specialist. |
| `Adviser` | Strategic guidance; has `Enricher` sub-agent. |
| `Generator` | Decomposes a task into subtasks. |
| `Refiner` | Patches subtask plans. |
| `Reporter` | Final task report assembly. |
| `Reflector` | Repairs non-tool-call LLM responses. |
| `Summarizer` | Condenses long context chains. |
| `ToolCallFixer` | Repairs malformed tool calls. |
| `Assistant` | Interactive conversational agent. |
| `Enricher` | Sub-agent of Adviser — context enrichment. |

All agents share a universal `perform_agent_chain()` loop (`securagentx/agents/base.py`) with iteration caps (100 general, 20 limited), Reflector injection on no-tool-call turns, Summarizer on context overflow, and a back-propagation state machine (`created → running → waiting → finished|failed`).

### 4.5 The Tools System — `AVAILABLE_TOOLS` + `ToolRegistry`

VulnAgent's tool catalog is defined declaratively in `securagentx/agent/vuln_agent.py:AVAILABLE_TOOLS` — a list of tool dicts with `name`, `description`, `parameters` (JSON Schema), and `handler_name`. The catalog mixes:

- **17 builtins** — `port_scan`, `web_recon`, `vuln_scan`, `search_cve`, `analyze_target`, `web_search`, `web_extract`, `read_file`, `write_file`, `edit_file`, `search_files`, `run_command`, `run_python`, `analyze_security`, `delegate`, plus `create_tool` and `edit_own_tool` for self-modification.
- **4 memory/skill tools** — `save_memory`, `recall_memory`, `list_memories`, `forget_memory` + 4 skill tools (`create_skill`, `view_skill`, `list_skills`, `delete_skill`).

`create_tool` lets the AI write a Python function at runtime and register it as a new callable tool; `edit_own_tool` patches an existing dynamically-created tool when the AI notices a bug. Both write through `_dynamic_tools` dict in VulnAgent so subsequent reasoning turns can call them.

The lower-level `securagentx/tools/__init__.py` provides `ToolRegistry`, `BaseTool` (abstract), `ToolMetadata`, and `ToolResult` dataclasses — the substrate used by `tools/*.py` (100+ modules) for non-AI-driven scans (BOLA harness, WAF evasion, smart recon, SAST, etc.). The CLI command `securagentx list-tools` enumerates both layers.

### 4.6 MCP Integration — `mcp/`

SecurAgentX is both an **MCP server** (exposing its 25 tools to external AI agents like Claude Desktop) and an **MCP client** (consuming tools from external MCP servers). All MCP code lives in the top-level `mcp/` package:

| Module | Responsibility |
|:-------|:---------------|
| `mcp/server.py:MCPServer` | Dynamically registers every entry in `AVAILABLE_TOOLS` as an MCP tool (prefixed `securagentx_`). Two transports: **stdio** (for Claude Desktop / local agent integration) and **HTTP** (REST API on port 8080). Resolves handlers at call time so dynamic tools created via `create_tool` are also reachable. |
| `mcp/manager.py:MCPManager` | Lifecycle manager — `start()` spawns the server in a daemon thread; `stop()` shuts it down. Called by `commands/mcp_runner.py:start_mcp_if_enabled()` on every CLI boot. Idempotent (singleton `_MCP_STARTED` guard). |
| `mcp/client.py:MCPClient` | Connects to external MCP servers (stdio subprocess or HTTP) so VulnAgent can call foreign tools. Implements `initialize` → `list_tools` → `call_tool` JSON-RPC handshake. |
| `mcp/protocol.py:MCPProtocol` | JSON-RPC 2.0 protocol implementation — `MCPRequest`, `MCPResponse`, `MCPTool` dataclasses + request/response framing. |
| `mcp/config.py:MCPConfigManager` | Loads config from `~/.securagentx/mcp.json` (user, gitignored) → project `mcp.json` → `config.yaml` → defaults. Template `mcp.json.example` ships in the repo and is auto-copied on first run. |

**Default MCP servers** (from `mcp.json.example`): `sequential-thinking`, `chain-of-recursive-thoughts`, `mcp-structured-thinking`, `memory`. Each is an `npx`-spawned local server. Configuration via TUI (`Ctrl+, → MCP Servers`) or by editing `~/.securagentx/mcp.json` directly.

### 4.7 Memory System — Cross-Session Recall

SecurAgentX maintains **four** persistent stores that together implement genuine cross-session learning:

| Store | Backend | Path | Purpose |
|:------|:--------|:-----|:--------|
| **VectorMemory** | ChromaDB | `~/.securagentx/data/memory/` | Semantic search over past findings, strategies, target patterns. Four collections: `working_memory`, `episodic_memory`, `semantic_memory`, `constitutional_memory`. |
| **JSON memory** | `memory.json` | `~/.securagentx/data/memory.json` | Fast keyword-indexed recall of recent findings + strategies (used when ChromaDB is unavailable). |
| **SkillStore** | `skills.json` | `~/.securagentx/data/skills.json` | Reusable named procedures the AI saved (`create_skill`) — step-by-step playbooks, exploit code, hard-won techniques. |
| **Knowledge Graph** | NetworkX + SQLite | `~/.securagentx/data/knowledge_graph.db` | Structured entity-relationship graph (IPs, domains, CVEs, services, vulnerabilities). |

The agent-facing API is `securagentx/agent/memory.py:AgentMemory`, which lazy-imports ChromaDB and falls back to JSON-only mode if the embedding model isn't downloaded. The lifecycle:

- **`pre_hunt(target)`** — recalled memories are injected into the AI system prompt so the agent starts with prior context.
- **`post_step(step, ...)`** — every action+result pair is auto-stored.
- **`post_hunt(report)`** — final findings are stored; successful techniques trigger `SkillStore.create()` to save a reusable skill.
- **`get_context(target)`** — formats memories as a context block for the next AI turn.

The deeper `securagentx/memory.py:CognitiveMemoryManager` provides the same interface but backed by `MemoryBackend` ABC with `VectorMemoryBackend` (ChromaDB) and a pluggable `SQLiteFTSBackend`. Memory entries carry `category` (working/episodic/semantic/constitutional), `importance` (0.0–1.0), `tags`, and access-count metadata for decay-based retrieval.

### 4.8 Knowledge Graph — `securagentx/knowledge_graph/`

A self-contained, dependency-light port of PentAGI's Graphiti/Neo4j layer. Backed by **NetworkX** (in-memory `MultiDiGraph`) + **SQLite** (persistence via `aiosqlite`), scoped per engagement by `group_id = f"flow-{flow_id}"`.

| Module | Responsibility |
|:-------|:---------------|
| `graph.py` | Core primitives: `Node`, `Edge`, `NodeLabel` (IP_ADDRESS, SERVICE, VULNERABILITY, …), `EdgeType` (HAS_PORT, EXPLOITS, MENTIONS, WORKS_ON, DISCOVERED_BY, RELATED_TO), `Episode`, `Community`, and `KnowledgeGraph` class. Implements all **7 PentAGI search strategies**: `temporal_window_search`, `entity_relationships_search`, `diverse_results_search` (MMR-reranked), `episode_context_search`, `successful_tools_search`, `recent_context_search`, `entity_by_label_search`. |
| `extractor.py` | `EntityExtractor` — regex + LLM extraction of entities (IPs, domains, URLs, ports, CVEs, hashes, credentials, file paths, service banners, emails) and relationships from agent responses and tool outputs. |
| `integration.py` | `KnowledgeGraphIntegration` — wires the extractor + graph into VulnAgent's loop via `on_agent_response`, `on_tool_execution`, `on_finding_discovered`, and `get_relevant_context` hooks. All hooks are no-ops when the KG is disabled, so VulnAgent runs unchanged with or without it. |
| `community.py` | `CommunityDetector` — NetworkX Louvain (greedy-modularity fallback) over per-flow subgraphs; LLM-summarised and merged communities reduce graph noise. |

The graph is ingested automatically: every agent response and every tool execution triggers `ingest_agent_response()` / `ingest_tool_execution()` (templates ported verbatim from PentAGI's `agent_response.tmpl` and `tool_execution.tmpl`). The KG then feeds back via `get_relevant_context(target)` which injects neighbouring entities into the AI system prompt — closing the **Brain → Tools → Memory → Knowledge Graph** loop shown in §4.1.

### 4.9 Governance & Constitution

Every action passes through two safety layers before execution:

- **`securagentx/governance.py:GovernanceGate`** — classifies shell commands into `SAFE` (run now), `PRIVILEGED` (ask), `DESTRUCTIVE` (popup with Allow / Allow Always / Deny). Examples: `nmap` → SAFE, `sudo apt install` → PRIVILEGED, `rm -rf /` → DESTRUCTIVE.
- **`securagentx/constitution.py` + `constitution_engine.py:ConstitutionalAIEngine`** — a principles document ("Do No Harm", "Respect Scope", "Be Truthful", "Proportionality", "Transparency", "Accountability", "Minimize Intrusion") that scores every proposed AI action via LLM review. If `guidance.requires_human_review` is true, `TrueAgenticLoop._request_human_review()` pauses the mission.

The constitution is binding: even in `--mode auto`, constitutional violations halt the agent. The constitutional oath is stored in `constitutional_memory` (one of the four ChromaDB collections) so the agent recalls it across sessions.

### 4.10 Module Conventions

| Convention | Value |
|:-----------|:------|
| CLI entry script | `securagentx` (console_script → `main:main`) |
| Module invocation | `python -m securagentx` (→ `securagentx/__main__.py` → `main.main()`) |
| Canonical package | `securagentx/` |
| Runtime data dir | `~/.securagentx/` (memory, skills, reports, logs, mcp.json, .env, config.yaml) |
| Memory backend | ChromaDB persistent client at `~/.securagentx/data/memory/` |
| Knowledge graph DB | `~/.securagentx/data/knowledge_graph.db` (SQLite) |
| GitHub URL | https://github.com/moussa12345678/SecurAgentX |
| License | GPL-3.0-only |

The old script-driven pipeline (`pipeline/phase_registry`, `pipeline/unified`, `core/brain.py`) has been **fully removed**. SecurAgentX now runs on a pure AI agent architecture: VulnAgent reasons, the loop iterates, the constitution guards, and the knowledge graph remembers.
