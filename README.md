# SecurAgentX

<div align="center">

<img src="assets/securagentx.png" alt="SecurAgentX" width="700">

<img src="assets/typing-animation.svg" alt="Terminal" width="700">

### Autonomous AI Security Research Framework

*Reasoning-driven vulnerability discovery that thinks like a penetration tester.*

[![Python](https://img.shields.io/badge/Python-3.10+-white?style=for-the-badge&logo=python&logoColor=red)](https://python.org)
[![License](https://img.shields.io/badge/License-GPL_3.0-red?style=for-the-badge)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-3000%2B%20passing-white?style=for-the-badge)](https://github.com/moussa12345678/SecurAgentX/actions)
[![MCP](https://img.shields.io/badge/MCP-Supported-red?style=for-the-badge)](https://modelcontextprotocol.io)
[![Security](https://img.shields.io/badge/Security-Governance-red?style=for-the-badge)](https://github.com/moussa12345678/SecurAgentX)

</div>

<img src="assets/red-divider.svg" width="100%">

## What is SecurAgentX?

SecurAgentX is a **true autonomous AI agent** for security research. It doesn't follow checklists or script chains — it **reasons** about targets, **chooses** its own tools, **pivots** when stuck, and **writes new tools** when existing ones aren't enough.

```text
User: "Find vulnerabilities in example.com"
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  VulnAgent — True AI Agent (free will, 25 tools)             │
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
│  └── DESTRUCTIVE → Block with popup                          │
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
pip install securagentx
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
│  VulnAgent uses 25 available tools...                        │
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

### True AI Agent Architecture

SecurAgentX uses **VulnAgent** — a genuine autonomous AI agent with **free will** over tool selection and execution flow:

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
- **25 built-in tools** — from port scanning to fuzzing, all described for AI consumption
- **`edit_own_tool`** — AI can create and modify its own tools at runtime
- **`create_tool`** — AI can author arbitrary Python tools on the fly
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
| **DESTRUCTIVE** | Auto-deny (blocked unconditionally) | `rm -rf /`, `dd`, `mkfs` |

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
                                              25 dynamic tools         REST API
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

## CLI Commands

### Core

```bash
securagentx hunt <target>       # Autonomous AI vulnerability hunt (VulnAgent)
securagentx scan <target>        # AI-driven scan (equivalent to hunt)
securagentx vuln-hunt <target>   # Full autonomous vulnerability hunting
securagentx tui                  # Textual TUI (chat interface)
securagentx configure            # Setup wizard
securagentx doctor               # System health check
```

**All scan/hunt commands now use VulnAgent** — the same true AI agent with 25 tools, memory, and free will. No script chains, no forced phases.

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
│  (True AI Agent)     │          │  (Background daemon)     │
│                      │          │                          │
│   AVAILABLE_TOOLS    │          │  stdio transport         │
│   ├─ 15 builtin     │          │  HTTP transport          │
│   ├─ 4 memory       │          │  25 dynamic tools        │
│   ├─ 4 skill        │          └──────────────────────────┘
│   ├─ 2 meta         │
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
# Full test suite (3000+ tests)
python3 -m pytest tests/ -v

# Stable suite (no network required)
python3 -m pytest tests/test_securagentx_paths.py tests/test_securagentx_scope.py tests/test_securagentx_governance.py -v
```

**3000+ tests** covering: governance, shell execution, target validation, MCP protocol, VulnAgent tools, agent memory, agent skills, the SecurAgentX path/scope/governance layer, and more.

<img src="assets/red-divider.svg" width="100%">

## Project Structure

```text
SecurAgentX/
├── main.py                 # CLI entry point
├── commands/               # CLI command handlers
│   ├── scan.py             # AI-driven scan (VulnAgent)
│   └── mcp_runner.py       # MCP auto-start helper
├── securagentx/              # Canonical module location
│   ├── agent/              # True AI agent (VulnAgent)
│   │   ├── __init__.py     # Exports VulnAgent
│   │   ├── vuln_agent.py   # Main agent + 25 tools
│   │   ├── agent_memory.py # JSON-backed memory store
│   │   ├── agent_skills.py # JSON-backed skill store
│   │   └── memory.py       # ChromaDB + FTS5 memory
│   ├── scope.py            # Target validation & scope
│   ├── paths.py            # Path resolution (SECURAGENTX_HOME / SECURAGENTX_DIRS)
│   ├── governance.py       # Governance layer
│   ├── scanning/           # Scanning subsystems
│   ├── brain.py            # Hybrid brain (deprecated)
│   └── loop.py             # Main agent loop
├── mcp/                    # MCP integration
│   ├── server.py           # MCP server (25 dynamic tools)
│   ├── client.py           # MCP client
│   ├── config.py           # MCP configuration
│   └── manager.py          # MCP lifecycle
├── tools/                  # 100+ tool modules
├── cli/                    # UI components + TUI (textual.py)
├── core/                   # Legacy (deprecated stubs)
├── pipeline/               # LEGACY: only scope.py remains
├── tests/                  # 3000+ tests
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
4. Run `python3 -m pytest tests/ -v` before pushing; all collected tests must pass (3117).
5. Open a pull request against `main`; CI runs the full SecurAgentX test matrix.

See [SECURITY.md](SECURITY.md) for responsible-disclosure and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community standards.

<img src="assets/red-divider.svg" width="100%">

## Acknowledgments

SecurAgentX builds on ideas and tooling from the broader security-research community:

- The **Model Context Protocol** spec — `securagentx` ships an auto-starting MCP server on every run.
- **ChromaDB** for the cross-session vector memory that powers `securagentx` recall.
- **Textual** for the `securagentx tui` chat interface.
- **PentAGI / vxcontrol** — original autonomous security agent framework that inspired SecurAgentX
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
