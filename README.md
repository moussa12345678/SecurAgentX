# SecurAgentX

<div align="center">

<img src="assets/securagentx.png" alt="SecurAgentX" width="700">

<img src="assets/typing-animation.svg" alt="Terminal" width="700">

### Autonomous AI Security Research Framework

> **Attribution:** This project is a modified derivative of [Elengenix](https://github.com/Ashveil1/Elengenix) by [Ashveil1](https://github.com/Ashveil1), licensed under GPL-3.0.

*Reasoning-driven vulnerability discovery that thinks like a penetration tester.*

[![Python](https://img.shields.io/badge/Python-3.10+-white?style=for-the-badge&logo=python&logoColor=red)](https://python.org)
[![License](https://img.shields.io/badge/License-GPL_3.0-red?style=for-the-badge)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-2600%2B%20passing-white?style=for-the-badge)](https://github.com/moussa12345678/SecurAgentX/actions)
[![MCP](https://img.shields.io/badge/MCP-Supported-red?style=for-the-badge)](https://modelcontextprotocol.io)
[![Security](https://img.shields.io/badge/Security-Governance-red?style=for-the-badge)](https://github.com/moussa12345678/SecurAgentX)

</div>

<img src="assets/red-divider.svg" width="100%">

## What is SecurAgentX?

SecurAgentX is an **autonomous AI agent** for security research. It doesn't follow checklists or script chains — it **reasons** about targets, **chooses** its own tools, **pivots** when stuck, and **writes new tools** when existing ones aren't enough.

```text
User: "Find vulnerabilities in example.com"
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  VulnAgent — Autonomous AI Agent (tool-selection autonomy, 27 tools) │
│  ├── Reasons about target and builds strategy                │
│  ├── Selects tools from AVAILABLE_TOOLS (freedom to skip)    │
│  ├── Creates new tools on the fly (edit_own_tool)            │
│  ├── Learns from cross-session memory (ChromaDB + Skills)    │
│  └── Pivots freely — no locked phases or forced ordering     │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  Governance Layer                                            │
│  ├── SAFE → Execute immediately                              │
│  ├── PRIVILEGED → Ask user approval                          │
│  └── DESTRUCTIVE → Auto-deny (blocked by default)            │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
Reports: findings, CVSS scores, AI analysis
```

Unlike "script chaining with an AI on top", SecurAgentX gives the AI **genuine autonomy** — it decides what to do, in what order, and how to adapt when a path fails.

<img src="assets/red-divider.svg" width="100%">

## Quick Start

### Requirements

- **Python 3.10+** (tested on 3.10, 3.11, 3.12, 3.13, 3.14)
- **Linux / macOS** (POSIX); Windows users should run inside WSL2
- **Optional**: Docker (for sandboxed shell execution), ChromaDB (for vector memory)
- An AI provider API key (Gemini recommended; see `securagentx configure`)

### Install

```bash
git clone https://github.com/moussa12345678/SecurAgentX.git
cd SecurAgentX && pip install -e .[dev]
```

### First Run

```bash
# System health check
securagentx doctor

# Configure AI providers
securagentx configure

# Start an autonomous vulnerability hunt
securagentx hunt example.com
```

### Terminal Demo

```text
┌─────────────────────────────────────────────────────────────┐
│  $ securagentx hunt example.com                                │
│                                                              │
│  ╔═══════════════════════════════════════════════════════╗   │
│  ║  SECURAGENTX HUNT — Autonomous AI Vulnerability Hunter   ║   │
│  ╚═══════════════════════════════════════════════════════╝   │
│                                                              │
│  [INFO] Starting autonomous AI hunt...                       │
│  [INFO] Target: example.com                                  │
│  [INFO] Cross-session memory: ACTIVE                         │
│                                                              │
│  VulnAgent uses 27 available tools...                        │
│  ├── Reasoning: Reconnaissance needed first                  │
│  ├── Scanning subdomains...                                  │
│  ├── Testing endpoints for common vulnerabilities...         │
│  ├── [FOUND] SQL injection at /api/users?id=                 │
│  ├── Creating custom exploit script...                       │
│  └── Report generated with findings                          │
│                                                              │
│  [OK] Hunt complete!                                         │
│  [OK] Report: ~/.securagentx/reports/hunt_example_com.md         │
└─────────────────────────────────────────────────────────────┘
```

<img src="assets/red-divider.svg" width="100%">

## Features

### Autonomous AI Agent Architecture

The original uses **VulnAgent** — an autonomous AI agent with **tool-selection autonomy** over tool selection and execution flow:

```
┌──────────────────────────────────────────────────────────────┐
│                    AI REASONING CYCLE                         │
│                                                              │
│   [REASON] ──► [TOOL SELECT] ──► [EXECUTE] ──► [ADAPT]     │
│      │                                          │            │
│      └──────────────────────────────────────────┘            │
│                    (continuous loop)                          │
└──────────────────────────────────────────────────────────────┘
```

- **No script chains** — AI decides every step, no locked phase ordering
- **27 built-in tools** — from port scanning to fuzzing, browser automation, knowledge graph, delegate, plus `create_tool` / `edit_own_tool` for runtime tool authoring
- **`edit_own_tool`** — AI can create and modify its own tools at runtime
- **`create_tool`** — AI can author arbitrary Python tools on the fly
- **`delegate`** — AI can delegate sub-tasks to specialist agents in `--multi-agent` mode
- **`browser`** — Playwright headless Chromium for JS-rendered pages (navigate, click, type, screenshot)
- **`knowledge_graph`** — Build and query a graph of targets, assets, findings, and CVEs across sessions
- **Cross-session Memory** — Remembers what worked (ChromaDB + Skills JSON store)
- **MCP Auto-start** — MCP server boots in background with every command

### Memory & Skills

SecurAgentX maintains two persistent stores:

| Store | Format | What it does |
|:-----:|:------:|--------------|
| **Memory** | `~/.securagentx/data/memory.json` | Saves findings, strategies, target patterns across sessions |
| **Skills** | `~/.securagentx/data/skills.json` | Stores reusable tool scripts, exploits, and techniques |

The AI can `memorize()`, `recall()`, `forget()`, `save_skill()`, `recall_skill()`, and `list_skills()` — building up a personal knowledge base over time.

### Safety by Design

Every command passes through a **Governance Layer** before execution:

| Risk Level | Action | Example |
|:----------:|--------|---------|
| **SAFE** | Execute immediately | `nmap`, `curl`, `python3` |
| **PRIVILEGED** | Ask user approval | `sudo apt install`, `pip install` |
| **DESTRUCTIVE** | Auto-deny (blocked by default; see Governance) | `rm -rf /`, `dd`, `mkfs` |

### MCP Integration

Full support for Model Context Protocol — auto-starts in the background on every command:

```
securagentx scan example.com
    │
    ▼
main() ──► show_banner() ──► start_mcp_if_enabled() ──► MCPServer (2 transports)
                                                                │
                                                     ┌──────────┴──────────┐
                                                     ▼                     ▼
                                              stdio (Claude Desktop)   HTTP (port 8080)
                                              27 dynamic tools         REST API
```

Configure MCP servers via:
```bash
# Via TUI (Ctrl+, → MCP Servers)
# Or edit mcp.json directly
```

Default MCP servers included:
- `sequential-thinking` — Structured problem-solving
- `chain-of-recursive-thoughts` — Deep recursive analysis
- `mcp-structured-thinking` — Step-by-step planning
- `memory` — Cross-session memory

<img src="assets/red-divider.svg" width="100%">

## What's New in SecurAgentX (vs. upstream PentAGI/Elengenix)

SecurAgentX builds on the original Elengenix/PentAGI foundation with significant enhancements:

### 🆕 New Features

| Feature | Description |
|---|---|
| **47 Security Tools** | 17 original + 30 new CLI tools (nmap, sqlmap, nikto, nuclei, ffuf, gobuster, etc.) |
| **Multi-Agent Mode** | `--multi-agent` flag activates FlowManager with specialist agents (Generator, Refiner, Reporter, Coder, Pentester, Searcher, Installer) + Docker sandbox |
| **YOLO Mode** | `--yolo` flag disables all AI script safety scanning — AI can run any code |
| **Hunt Planning** | 5 mandatory pre-hunt skills loaded before every scan (red team, hacking workflow, bug bounty, OWASP Top 10, pentest checklist) |
| **500+ Skills Library** | 501 JSON skills across 10 domains (recon, web, network, cloud, mobile, crypto, exploit, post-exploit, reporting, auth, API) |
| **LLM Adapter** | `UniversalAIClientAdapter` bridges sync `.chat()` to async `.call()` Protocol |
| **429 Retry/Backoff** | 20 attempts × 60s wait — patient retry on rate limits |
| **Scope Advisory** | Non-blocking scope checks (proceeds with warning, doesn't block IPs) |
| **Fast Port Scan** | Socket-based port scanning (25 ports in ~50s, was 5+ min with omni_scan) |
| **REST API + GraphQL** | FastAPI server with rate limiting (5/min login, 10/min flows) |
| **Observability** | OpenTelemetry + Langfuse tracing auto-setup |
| **Knowledge Graph** | Cross-session target/asset/CVE graph with NetworkX + SQLite |
| **Browser Automation** | Playwright headless Chromium for JS-rendered pages |
| **Docker Sandbox** | Isolated execution environment for privileged operations |
| **max_steps=100** | 4× deeper scans (was 25 in upstream) |

### 🔒 Security Hardening

| Fix | Description |
|---|---|
| **Path Traversal Guard** | Docker file ops reject `..` paths |
| **SSRF Protection** | Scheme allowlist + IPv6-mapped IPv4 unwrap |
| **Package Validation** | Regex allowlist for package manager names |
| **Rate Limiting** | In-memory token bucket on API endpoints |
| **Sudo Password Safety** | Passwords via subprocess stdin, never in command string |
| **Auto-Approve TTL** | 5-minute expiry on governance auto-approve |

### 📊 SAST Clean

| Tool | Result |
|---|---|
| ruff F-rules | ✅ 0 errors |
| bandit HIGH | ✅ 0 |
| pylint E-errors | ✅ 0 |
| vulture ≥80% | ✅ 0 |
| detect-secrets | ✅ 0 real secrets |
| CI | ✅ 4/4 green (Python 3.11/3.12/3.13) |

<img src="assets/red-divider.svg" width="100%">

## CLI Commands

### Core

```bash
securagentx hunt <target>       # Autonomous AI vulnerability hunt (VulnAgent)
securagentx scan <target>        # AI-driven scan (equivalent to hunt)
securagentx vuln-hunt <target>   # Full autonomous vulnerability hunting
securagentx hunt <target> --multi-agent   # Multi-agent FlowManager mode (specialists + Docker sandbox)
securagentx hunt <target> --yolo           # YOLO mode: disable all safety scanning
securagentx tui                  # Textual TUI (chat interface)
securagentx configure            # Setup wizard
securagentx doctor               # System health check
securagentx api                  # Start REST API + GraphQL server (FastAPI)
```

**All scan/hunt commands now use VulnAgent** — the same AI agent with 27 tools, memory, and tool-selection autonomy. No script chains, no forced phases.

Pass `--multi-agent` to `hunt` or `vuln-hunt` to switch from single-agent mode to the multi-agent `FlowManager` (uses `securagentx/flows/` + `ConcreteFlowProvider` + specialist agents + Docker sandbox).

Pass `--yolo` to disable all AI script safety scanning. The AI can then run ANY Python code without restriction. **ONLY use this with explicit written authorization!**

### Multi-target

```bash
securagentx hunt "example.com, api.example.com"
```

### Shortcuts

| Shortcut | Expands to | Description |
|:--------:|------------|-------------|
| `bb` | `scan --phase bola` | BOLA testing *(deprecated — redirects to VulnAgent)* |
| `check` | `scan --phase recon` | Quick recon *(deprecated — redirects to VulnAgent)* |
| `test` | `scan --phase waf` | WAF detection *(deprecated — redirects to VulnAgent)* |

<img src="assets/red-divider.svg" width="100%">

## Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                        main.py                               │
│                    (CLI Entry Point)                          │
│  ┌─ MCP auto-start (every boot)                              │
└──────────────────────────┬───────────────────────────────────┘
                           │
          ┌────────────────┴────────────────┐
          ▼                                 ▼
┌─────────────────────┐          ┌─────────────────────────┐
│  VulnAgent           │          │  MCP Server              │
│  (Autonomous AI Agent) │          │  (Background daemon)     │
│                      │          │                          │
│   AVAILABLE_TOOLS    │          │  stdio transport         │
│   ├─ 14 builtin     │          │  HTTP transport          │
│   ├─ browser        │          │  27 dynamic tools        │
│   ├─ delegate       │          │  REST API + GraphQL      │
│   ├─ knowledge_graph│          └──────────────────────────┘
│   ├─ 4 memory       │
│   ├─ 4 skill        │
│   ├─ create_tool    │
│   └─ edit_own_tool  │
└──────────┬───────────┘
           │
           ▼
┌─────────────────────┐
│  AgentMemory         │
│  ├─ ChromaDB (FTS5) │
│  └─ JSON stores     │
└─────────────────────┘
```

The old script-driven pipeline (`pipeline/phase_registry`, `pipeline/unified`) has been removed. The legacy `core/brain.py` shim remains for backward compatibility — new code should use `securagentx/brain.py` instead.

<img src="assets/red-divider.svg" width="100%">

## Configuration

### MCP Servers (mcp.json)

```json
{
  "mcpServers": {
    "sequential-thinking": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-sequential-thinking"]
    },
    "chain-of-recursive-thoughts": {
      "type": "local",
      "command": ["npx", "-y", "recursive-thinking-mcp"]
    },
    "mcp-structured-thinking": {
      "type": "local",
      "command": ["npx", "-y", "structured-thinking"]
    },
    "memory": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

Auto-copied from `mcp.json.example` on first run. User config overrides project config.

### AI Providers

Supported: OpenAI, Anthropic, Google Gemini, Groq, DeepSeek, Ollama (local), and more.

```bash
securagentx configure  # Interactive setup wizard
```

### Environment Variables

SecurAgentX reads runtime behaviour from `SECURAGENTX_*` environment variables (set them in `.env`):

| Variable | Purpose | Default |
|:---------|:--------|:--------|
| `SECURAGENTX_SCOPE` | Comma-separated allowed target domains | (none — scope.txt is used instead) |
| `SECURAGENTX_PLUGIN_PATH` | Extra plugin discovery path | (none) |
| `SECURAGENTX_DEFAULT_TARGET` | Default target used when none is given on CLI | (none) |
| `SECURAGENTX_RATE_LIMIT` | Max outbound requests per minute | `40` |
| `SECURAGENTX_SMART_SCAN` | Set to `1` to enable smart-scan optimisations in the bot integration | `0` |
| `SECURAGENTX_DEMO` | Set to any non-empty value to enable TUI demo mode | (unset) |

Plus per-provider API-key variables: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Never commit `.env` — it is gitignored.

### Config File (config.yaml)

SecurAgentX loads YAML config from `~/.securagentx/config.yaml` (auto-created from `config.yaml.example` on first run). It contains agent limits, AI provider selection, Telegram bridge settings, and the optional TeamAegis 3-AI collaboration block (strategist / specialist / critic).

<img src="assets/red-divider.svg" width="100%">

## Testing

```bash
# Full test suite (2600+ tests)
python3 -m pytest tests/ -v

# Stable suite (no network required)
python3 -m pytest tests/test_securagentx_paths.py tests/test_securagentx_scope.py tests/test_securagentx_governance.py -v
```

**2600+ tests** covering: governance, shell execution, target validation, MCP protocol, VulnAgent tools (including `browser`, `knowledge_graph`, `delegate`), agent memory, agent skills, the SecurAgentX path/scope/governance layer, REST API, GraphQL, flows, Docker sandbox, observability, and more.

<img src="assets/red-divider.svg" width="100%">

## Project Structure

```text
SecurAgentX/
├── main.py                 # CLI entry point
├── commands/               # CLI command handlers
│   ├── scan.py             # AI-driven scan (VulnAgent)
│   └── mcp_runner.py       # MCP auto-start helper
├── securagentx/              # Canonical module location
│   ├── agent/              # Autonomous AI agent (VulnAgent)
│   │   ├── __init__.py     # Exports VulnAgent
│   │   ├── vuln_agent.py   # Main agent + 27 tools
│   │   ├── agent_memory.py # JSON-backed memory store
│   │   ├── agent_skills.py # JSON-backed skill store
│   │   └── memory.py       # ChromaDB + FTS5 memory
│   ├── agents/             # Multi-agent specialists + PrimaryAgent (used with --multi-agent)
│   ├── flows/              # FlowManager + ConcreteFlowProvider (multi-agent orchestration)
│   ├── api/                # REST API (FastAPI) — `securagentx api`
│   ├── graphql/            # GraphQL schema (mounted at /graphql)
│   ├── observability/      # OpenTelemetry + Langfuse tracing (auto-setup in main.py)
│   ├── docker/             # Docker sandbox for privileged agent shell execution
│   ├── browser/            # Playwright headless Chromium tool
│   ├── knowledge_graph/    # Cross-session target/asset/CVE graph
│   ├── scope.py            # Target validation & scope
│   ├── paths.py            # Path resolution (SECURAGENTX_HOME / SECURAGENTX_DIRS)
│   ├── governance.py       # Governance layer
│   ├── scanning/           # Scanning subsystems
│   ├── brain.py            # Hybrid brain (deprecated)
│   └── loop.py             # Main agent loop
├── mcp/                    # MCP integration
│   ├── server.py           # MCP server (27 dynamic tools)
│   ├── client.py           # MCP client
│   ├── config.py           # MCP configuration
│   └── manager.py          # MCP lifecycle
├── tools/                  # 100+ tool modules
├── cli/                    # UI components + TUI (textual.py)
├── core/                   # Legacy (deprecated stubs)
├── pipeline/               # LEGACY: only scope.py remains
├── tests/                  # 2600+ tests (+ brutal/ integration suite)
```

<img src="assets/red-divider.svg" width="100%">

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Core rules:**
- 4-space indentation
- Type hints everywhere
- Shell commands only behind Governance
- API keys in `.env` only
- AI agents get genuine autonomy — no forced tool ordering

**Workflow:**
1. Fork `moussa12345678/SecurAgentX` and create a feature branch.
2. Run `securagentx doctor` to confirm your dev environment.
3. Add or update tests under `tests/` — SecurAgentX requires new behaviour to be covered.
4. Run `python3 -m pytest tests/ -v` before pushing; all collected tests must pass (2600+).
5. Open a pull request against `main`; CI runs the full SecurAgentX test matrix.

See [SECURITY.md](SECURITY.md) for responsible-disclosure and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community standards.

<img src="assets/red-divider.svg" width="100%">

## Acknowledgments

SecurAgentX is a derivative work of **Elengenix** (https://github.com/Ashveil1/Elengenix) by **Ashveil1**, originally licensed under GPL-3.0. We gratefully acknowledge the original work.

SecurAgentX builds on ideas and tooling from the broader security-research community:

- The **Model Context Protocol** spec — `securagentx` ships an auto-starting MCP server on every run.
- **ChromaDB** for the cross-session vector memory that powers `securagentx` recall.
- **Textual** for the `securagentx tui` chat interface.
- The open-source security research community for inspiration and tooling
- Every contributor who has filed an issue or PR against `moussa12345678/SecurAgentX`.

Want to be listed here? Send a PR — see [Contributing](#contributing) above.

<img src="assets/red-divider.svg" width="100%">

## License

GPL-3.0 — see [LICENSE](LICENSE)

<img src="assets/red-divider.svg" width="100%">

<div align="center">

**Built for the open-source security community.**

[![GitHub Stars](https://img.shields.io/github/stars/moussa12345678/SecurAgentX?style=for-the-badge&color=red)](https://github.com/moussa12345678/SecurAgentX)
[![GitHub Issues](https://img.shields.io/github/issues/moussa12345678/SecurAgentX?style=for-the-badge&color=red)](https://github.com/moussa12345678/SecurAgentX/issues)
[![GitHub PRs](https://img.shields.io/github/issues-pr/moussa12345678/SecurAgentX?style=for-the-badge&color=red)](https://github.com/moussa12345678/SecurAgentX/pulls)

</div>
