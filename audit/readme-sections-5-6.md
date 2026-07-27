# README Sections 5 & 6 — Configuration and Testing

> **Task:** P10-C — Rewrite README preserving all SecurAgentX features. This file
> delivers Section 5 (Configuration) and Section 6 (Testing) ready to be spliced
> into the canonical `README.md` after the Elengenix→SecurAgentX rename.

---

## 5. Configuration

SecurAgentX is configured through three layers, layered from most-overriding to
least-overriding:

1. **Environment variables** — read at process start (via `python-dotenv` from
   `.env`). Highest priority for secrets and runtime flags.
2. **`config.yaml`** — read at startup by `securagentx.paths.find_config()`.
   Holds non-secret structural settings (agent limits, provider models, the
   TeamAegis multi-AI topology).
3. **`~/.securagentx/`** — the pip-safe user home. All persistent state (memory,
   skills, reports, flows.db, ChromaDB vectors) lives here, never in
   `site-packages`.

### 5.1 Configuration File Locations

SecurAgentX resolves its two config files using the same priority chain:

| File | Env-Var Override | Default Search Order |
|:-----|:-----------------|:---------------------|
| `.env` | `SECURAGENTX_ENV` | `$SECURAGENTX_ENV` → `~/.securagentx/.env` → `./.env` |
| `config.yaml` | `SECURAGENTX_CONFIG` | `$SECURAGENTX_CONFIG` → `~/.securagentx/config.yaml` → `./config.yaml` |

Both lookup helpers live in `securagentx/paths.py` (`find_env()`,
`find_config()`). Templates ship with the repo as `.env.example` and
`config.yaml.example` and are copied into `~/.securagentx/` on first run by
`main.py` if they are missing.

The full on-disk layout under `~/.securagentx/`:

```text
~/.securagentx/
├── .env                    # secrets (gitignored, never committed)
├── config.yaml             # structural config
├── mcp.json                # user MCP-server config (gitignored; overrides repo .mcp.json)
├── scope.txt               # allowed-scope domains (one per line)
├── data/
│   ├── memory.json         # VulnAgent key-value memory store (JSON)
│   ├── skills.json         # VulnAgent skill library (JSON)
│   ├── flows.db            # SQLite DB for the Flow / Task / Subtask hierarchy
│   ├── vector_memory/      # ChromaDB persistent vector store (cross-session memory)
│   └── logs/               # per-session log files
├── tools/                  # AI-authored tool scripts saved at runtime
├── reports/                # generated hunt/scan reports (Markdown + PDF)
├── scripts/                # user-installed helper scripts
└── plugins/                # third-party plugin packages
```

The five sub-directories (`data`, `tools`, `reports`, `scripts`, `plugins`)
are exposed to the rest of the codebase as the `SECURAGENTX_DIRS` mapping and
are created on boot by `securagentx.paths.ensure_dirs()`.

### 5.2 Environment Variables

All SecurAgentX-native variables use the `SECURAGENTX_*` prefix (the rename
from the legacy `ELENGENIX_*` prefix is complete — see `securagentx/paths.py`
and `tests/test_securagentx_paths.py`). Provider/integration keys keep their
upstream names (`OPENAI_API_KEY`, `GEMINI_API_KEY`, …) so they remain
compatible with the official SDKs.

#### 5.2.1 SecurAgentX-Native Variables

| Variable | Description | Default |
|:---------|:------------|:--------|
| `SECURAGENTX_HOME` | Root directory for all user data. Resolved at import time by `securagentx.paths`. | `~/.securagentx` |
| `SECURAGENTX_DIRS` | Python `dict` (not an env var read by the user) exposing the five sub-directories `data`, `tools`, `reports`, `scripts`, `plugins` under `SECURAGENTX_HOME`. Documented here for completeness. | derived from `SECURAGENTX_HOME` |
| `SECURAGENTX_ENV` | Explicit override path to a `.env` file. If set and the path exists, it wins over both `~/.securagentx/.env` and `./.env`. | *(unset — fall through to default search order)* |
| `SECURAGENTX_CONFIG` | Explicit override path to `config.yaml`. Same precedence rules as `SECURAGENTX_ENV`. | *(unset — fall through to default search order)* |
| `SECURAGENTX_SCOPE` | Comma-separated list of allowed target domains / IPs. Read by `securagentx.scope` and `pipeline.scope` when `scope.txt` is absent. Example: `SECURAGENTX_SCOPE=example.com, api.example.com`. | *(unset — fall through to `scope.txt`)* |
| `SECURAGENTX_DEFAULT_TARGET` | Default target applied by `securagentx configure` when no target is supplied on the command line. Saved by the config wizard (`tools/config_wizard.py`). | *(unset — no default target)* |
| `SECURAGENTX_RATE_LIMIT` | Per-provider rate limit in requests-per-minute. Validated as int by the config wizard. Recommended: `40` for production, `120` for testing. | `40` |
| `SECURAGENTX_TZ` | IANA timezone name (e.g. `Asia/Bangkok`, `UTC`) used by `agents/agent_helpers.py` and `securagentx/scanning/helpers.py` to localise timestamps in agent reasoning context. | *(unset — system local time)* |
| `SECURAGENTX_IN_TMUX` | Set to `1` to force-enable tmux detection in `cli/live_display.py` (used even when `$TMUX` is not propagated). | auto-detected from `$TMUX` |
| `SECURAGENTX_DEMO` | Set to any truthy value to enable the dashboard's demo mode (`tui/dashboard.py`). | *(unset)* |
| `SECURAGENTX_SMART_SCAN` | Set to `1` to enable smart-scan heuristics in `integrations/bot.py` and `main.py`. | *(unset)* |
| `SECURAGENTX_QUIET` | Set to `1` to suppress non-essential console output in `main.py`. | *(unset)* |
| `SECURAGENTX_BELL` | Set to `0` to disable the TUI terminal bell (`cli/textual.py`). The `--no-bell` CLI flag is equivalent. | *(unset — bell enabled)* |
| `SECURAGENTX_PLUGIN_PATH` | Extra filesystem path searched by `tools/ecosystem.py` for third-party plugin packages. | *(unset — only `SECURAGENTX_DIRS["plugins"]` is searched)* |
| `SECURAGENTX_SANDBOX_NO_NETWORK` | Set to `1` inside spawned sandbox subprocesses (`tools/ai_sandbox.py`) to signal that network access has been disabled and that well-behaved code should not attempt socket binds. Internal — not normally set by users. | *(unset — network allowed in sandbox)* |
| `SECURAGENTX_FLOWS_DB` | Override path for the Flow-management SQLite database (`securagentx/flows/db.py`). Resolution order: explicit constructor `db_path` arg → `SECURAGENTX_FLOWS_DB` → `~/.securagentx/data/flows.db`. | `~/.securagentx/data/flows.db` |

> **Internal-use only.** Two `__SECURAGENTX_*` (double-underscore prefix)
> variables are used internally by `securagentx/agent/vuln_agent.py` to pass
> state into spawned subprocesses — `__SECURAGENTX_CWD` (working directory)
> and `__SECURAGENTX_AI_CONFIG` (JSON-serialised AI provider config). These are
> not user-facing and should not be set manually.

#### 5.2.2 Provider & Integration Variables

These follow the upstream SDK naming conventions so they work with the official
OpenAI / Anthropic / Google / Groq clients unchanged.

| Variable | Description | Default |
|:---------|:------------|:--------|
| `AI_PROVIDER` | Active AI provider selector. Accepted values: `gemini`, `openai`, `anthropic`, `groq`, `local`, `openrouter`. | `gemini` |
| `GEMINI_API_KEY` | Google Gemini API key (recommended default provider). | — |
| `OPENAI_API_KEY` | OpenAI API key (e.g. `sk-...`). | — |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key (e.g. `sk-ant-...`). | — |
| `GROQ_API_KEY` | Groq API key (e.g. `gsk_...`). | — |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token for the optional notification integration. | — |
| `TELEGRAM_CHAT_ID` | Telegram chat ID to receive notifications. | — |
| `HACKERONE_API_KEY` | HackerOne API key for the bug-bounty integration (saved by `securagentx configure`). | — |
| `HACKERONE_API_USER` | HackerOne API user handle. | — |

### 5.3 `config.yaml` — Structural Configuration

Annotated template (mirrors `config.yaml.example` shipped with the repo):

```yaml
# ═══════════════════════════════════════════════════════
# SecurAgentX Configuration Template
#  SECURITY: Never store real keys here. Use .env instead.
# ═══════════════════════════════════════════════════════

agent:
  max_output_chars: 4000     # Truncation threshold for AI tool output
  max_steps: 20              # Max agent reasoning steps per hunt
  timeout_seconds: 90        # Wall-clock timeout per agent invocation

ai:
  # Selected provider: openai, gemini, anthropic, groq, local, openrouter
  active_provider: gemini

  providers:
    gemini:
      model: gemini-1.5-flash
      # api_key: read from $GEMINI_API_KEY (never inline it here)

    openai:
      model: gpt-4o-mini
      # api_key: read from $OPENAI_API_KEY

    anthropic:
      model: claude-3-5-sonnet-latest

    groq:
      model: llama-3.3-70b-versatile

    local:
      base_url: http://localhost:11434/v1   # Ollama / vLLM endpoint
      model: llama3.2

telegram:
  # bot_token: read from $TELEGRAM_BOT_TOKEN
  # chat_id:    read from $TELEGRAM_CHAT_ID

# ═══════════════════════════════════════════════════════
# TeamAegis — Multi-AI Collaboration (3 AI Agents)
# ═══════════════════════════════════════════════════════
# When enabled, the hybrid hunt mode uses 3 separate AI
# models that collaborate: plan → execute → validate.
#
# Each role can use a different provider and model.
# If a role has no provider set, it falls back to the
# main active_provider above.
#
# Roles:
#   strategist — Plans the attack tree (high-level thinker)
#   specialist — Executes tools and shell commands
#   critic     — Validates findings, filters false positives
# ═══════════════════════════════════════════════════════
team_aegis:
  enabled: false             # Set to true to activate 3-AI mode

  strategist:
    provider: gemini         # Provider for planning AI
    model: gemini-2.0-flash  # Model name (optional override)

  specialist:
    provider: anthropic      # Provider for execution AI
    model: claude-3-5-haiku-20241022

  critic:
    provider: openai         # Provider for validation AI
    model: gpt-4o-mini

  # risk_threshold: critical  # When to require human approval
  #   "high"     = vote on HIGH + CRITICAL risk tasks
  #   "critical" = only CRITICAL tasks (default, less disruptive)
```

Secrets (`*_API_KEY`, `*_BOT_TOKEN`, `*_CHAT_ID`) are deliberately **not**
stored in `config.yaml` — the file is treated as shareable. The provider
configuration reads them at runtime from the environment (populated by
`python-dotenv` from `.env`).

### 5.4 MCP Server Configuration (`.mcp.json`)

SecurAgentX auto-starts a Model Context Protocol (MCP) server on every command.
The set of *external* MCP servers it connects to is configured in `mcp.json`.

**Resolution order** (in `mcp/config.py`):

1. `~/.securagentx/mcp.json` — user config (gitignored, takes precedence).
2. `<repo>/.mcp.json` — project config (committed template, auto-copied on
   first run).

The committed `.mcp.json` template ships with three ready-to-use servers:

```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/mnt/data/SecurAgentX"]
    },
    "git": {
      "command": "uvx",
      "args": ["mcp-server-git", "--repository", "/mnt/data/SecurAgentX"]
    }
  }
}
```

#### Default / Recommended MCP Servers

The following four MCP servers are the defaults SecurAgentX is designed around.
The three shipped in `.mcp.json` (`memory`, `filesystem`, `git`) cover the
baseline; enabling the additional reasoning servers below unlocks structured
planning workflows. Add or remove entries via the TUI (`Ctrl+,` → *MCP
Servers*) or by editing `~/.securagentx/mcp.json` directly.

| Server | Purpose | Install Command |
|:-------|:--------|:----------------|
| `sequential-thinking` | Structured step-by-step problem solving | `npx -y @modelcontextprotocol/server-sequential-thinking` |
| `chain-of-recursive-thoughts` | Deep recursive analysis with self-critique | `npx -y mcp-server-chain-of-recursive-thoughts` |
| `mcp-structured-thinking` | Step-by-step planning with revision history | `npx -y mcp-server-structured-thinking` |
| `memory` | Cross-session persistent memory (knowledge graph) | `npx -y @modelcontextprotocol/server-memory` |
| `filesystem` | Sandboxed filesystem access for the project root | `npx -y @modelcontextprotocol/server-filesystem /path/to/SecurAgentX` |
| `git` | Read-only git repository introspection | `uvx mcp-server-git --repository /path/to/SecurAgentX` |

User config (`~/.securagentx/mcp.json`) always overrides project config
(`<repo>/.mcp.json`), so customising the server list never touches the
committed template.

### 5.5 Cross-Session Memory Configuration (ChromaDB + JSON stores)

SecurAgentX maintains **two complementary memory subsystems**, both persisted
under `~/.securagentx/data/`:

#### 5.5.1 Vector Memory (ChromaDB, semantic)

`tools/vector_memory.py` exposes `VectorMemory`, a semantic vector store
backed by ChromaDB. It persists to:

```
~/.securagentx/data/vector_memory/
```

Configuration knobs:

| Setting | How to Override | Default |
|:--------|:----------------|:--------|
| Persist directory | Pass `persist_directory` to the `VectorMemory(persist_directory=...)` constructor. | `$SECURAGENTX_DIRS["data"] / "vector_memory"` (i.e. `~/.securagentx/data/vector_memory`) |
| Collection name | Hardcoded to `securagentx_memories` (see `_init_chromadb()`). | `securagentx_memories` |
| Telemetry | `anonymized_telemetry=False` (set in `Settings`). | disabled |
| Persistence mode | `is_persistent=True`. | persistent |

**Fallback behaviour.** If the `chromadb` package is not importable (e.g. a
minimal install), `VectorMemory` silently degrades to a SQLite FTS5-backed
fallback with the same API surface — zero extra dependencies, no data loss on
upgrade.

#### 5.5.2 Agent Memory & Skills (JSON, key-value)

`securagentx/agent/agent_memory.py` and `securagentx/agent/agent_skills.py`
each expose a lightweight JSON-backed store for flat facts/notes and reusable
tool scripts respectively.

| Store | Class | File | Description |
|:------|:------|:-----|:------------|
| Memory | `MemoryStore` | `~/.securagentx/data/memory.json` | Tagged key-value facts (findings, strategies, target patterns). API: `save`, `search`, `forget`. |
| Skills | `SkillStore` | `~/.securagentx/data/skills.json` | Reusable Python tool scripts authored by the agent at runtime. API: `save_skill`, `recall_skill`, `list_skills`. |

Both stores are loaded lazily on first access and write back atomically (temp
file + rename). Their root directory is `SECURAGENTX_HOME / "data"`, so
overriding `SECURAGENTX_HOME` relocates both files.

#### 5.5.3 Flow Database (SQLite, async)

`securagentx/flows/db.py` exposes `FlowDB`, an async SQLite-backed store for
the Flow → Task → Subtask hierarchy used by the TeamAegis multi-AI
collaboration mode. The DB path resolves as:

1. Explicit `db_path` argument to the `FlowDB` constructor, else
2. `SECURAGENTX_FLOWS_DB` environment variable, else
3. `~/.securagentx/data/flows.db` (default).

The schema mirrors PentAGI's PostgreSQL layout 1-to-1 (tables: `flows`,
`tasks`, `subtasks`, `msgchains`, `msglogs`, `agentlogs`, `toolcalls`,
`searchlogs`, `termlogs`, `vecstorelogs`, `screenshots`, `prompts`,
`containers`). Writes are serialised through an `asyncio.Lock` because SQLite
supports only one writer at a time.

### 5.6 AI Provider Configuration

SecurAgentX supports six provider backends, all configured via
`securagentx configure` (interactive) or by hand-editing `.env` +
`config.yaml`.

| Provider | `AI_PROVIDER` value | Required Env Var(s) | Default Model (`config.yaml`) |
|:---------|:--------------------|:--------------------|:------------------------------|
| Google Gemini | `gemini` | `GEMINI_API_KEY` | `gemini-1.5-flash` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet-latest` |
| Groq | `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| Local (Ollama / vLLM) | `local` | none — set `base_url` in `config.yaml` | `llama3.2` (`http://localhost:11434/v1`) |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` | *(user-set)* |

Per-role overrides for TeamAegis 3-AI mode live under `team_aegis.{strategist,
specialist,critic}` in `config.yaml` (see §5.3). Any role that omits `provider`
falls back to the top-level `ai.active_provider`.

To reconfigure at any time:

```bash
securagentx configure   # Interactive setup wizard (providers, rate limits,
                        # default target, Telegram, HackerOne)
securagentx doctor      # Health check — verifies provider keys, paths, MCP
```

---

## 6. Testing

### 6.1 Overview

SecurAgentX ships with a layered test suite totalling **3,042 test functions**
across **50 test files**, of which **1,406 are deep "brutal" tests** focused on
security, adversarial inputs, and integration edge cases. The suite is
designed to run in three modes:

- **Unit** — fast, hermetic, no network. The default for local development
  and the gate in CI.
- **Integration** — opt-in (`-m "integration"`), exercises real network
  services and live LLM endpoints. Allowed to fail in CI (`continue-on-error`).
- **Brutal** — deep security and integration-stress tests under
  `tests/brutal/`. Run as part of the unit suite by default.

### 6.2 Test Categories

| Category | Marker | Location | Network | CI Behaviour |
|:---------|:-------|:---------|:--------|:-------------|
| **Unit** | *(none — default)* | `tests/test_*.py` (45 files) | no | must pass on all matrix Python versions |
| **Integration** | `@pytest.mark.integration` | `tests/test_*.py` (mixed in) | yes | `continue-on-error: true` — failures do not break CI |
| **Brutal** | *(none — discovered by path)* | `tests/brutal/test_*.py` (5 files) | no (mocked) | must pass — counted in the unit gate |

The `integration` marker is registered in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: opt-in integration tests that hit real network/services (deselect with '-m \"not integration\"')",
]
```

#### 6.2.1 Brutal tests

The `tests/brutal/` directory contains the deep security/integration suite.
Files (5 total, 1,406 test functions):

| File | Focus |
|:-----|:------|
| `tests/brutal/test_agents_brutal.py` | VulnAgent reasoning loop, tool selection, autonomy edge cases |
| `tests/brutal/test_api_auth_brutal.py` | Authentication, authorisation, session/token tampering |
| `tests/brutal/test_docker_brutal.py` | Container/sandbox lifecycle, resource limits, escape attempts |
| `tests/brutal/test_integration_security_brutal.py` | End-to-end security: prompt injection, CVSS scoring, report rendering, templates, export pipeline |
| `tests/brutal/test_kg_flows_providers_brutal.py` | Knowledge-graph flows, search-provider registry, adversarial query handling |

`tests/brutal/conftest.py` mirrors the project-root `tests/conftest.py` to
ensure the `securagentx` package is importable when pytest is invoked from a
sub-directory.

### 6.3 Test Counts

| Scope | Test Functions | Test Files |
|:------|---------------:|-----------:|
| `tests/` top-level (excl. `brutal/`) | 1,636 | 45 |
| `tests/brutal/` | 1,406 | 5 |
| **Total** | **3,042** | **50** |

Counts are stable: `grep -rE "^\s*(async )?def test_" tests/ | wc -l` returns
3,042. Pytest's own collection (`pytest --collect-only -q`) reports 2,888
after its deselection rules (parameter sub-cases, marker filters).

### 6.4 Running Tests Locally

#### 6.4.1 Install dev dependencies

```bash
pip install -e ".[dev]"
# Or the minimal test runner set:
pip install pytest pytest-asyncio pytest-timeout rich
```

#### 6.4.2 Full hermetic suite (no network — the CI gate)

```bash
# All non-integration tests, including brutal/, with a 300s per-test timeout
python -m pytest tests/ -v -m "not integration" --timeout=300 --tb=short
```

#### 6.4.3 Stable subset (fastest feedback loop)

```bash
python -m pytest tests/test_tui.py tests/test_security.py tests/test_core_modules.py -v
```

#### 6.4.4 Brutal suite only

```bash
python -m pytest tests/brutal/ -v --timeout=300
```

#### 6.4.5 Integration tests (network required)

```bash
python -m pytest tests/ -v -m "integration" --tb=short
```

#### 6.4.6 Coverage report

```bash
pip install pytest-cov
python -m pytest tests/ -m "not integration" \
    --cov=securagentx --cov=tools --cov=mcp --cov=commands \
    --cov-report=term-missing --cov-report=html
# Open htmlcov/index.html for the line-by-line report.
```

### 6.5 Pytest Configuration

Pytest is configured in two places — `pytest.ini` (legacy, repo-root) and
`pyproject.toml` `[tool.pytest.ini_options]` (modern). Both apply; the
`pyproject.toml` values take precedence on conflict.

#### `pytest.ini`

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
filterwarnings =
    ignore::DeprecationWarning
```

#### `pyproject.toml` (pytest section)

```toml
[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "integration: opt-in integration tests that hit real network/services (deselect with '-m \"not integration\"')",
]
```

Key behaviours:

- **`asyncio_mode = auto`** — `async def test_*` functions are run via
  `pytest-asyncio` without needing an explicit `@pytest.mark.asyncio`
  decorator.
- **`testpaths = ["tests"]`** — pytest discovers tests only under `tests/`,
  preventing accidental collection of helper modules in `tools/` or `agents/`.
- **`filterwarnings = ignore::DeprecationWarning`** — keeps the test output
  readable when upstream libraries emit deprecation noise.
- **`markers.integration`** — opt-in marker for network-dependent tests.

### 6.6 Test Fixtures

#### `tests/conftest.py`

A minimal sys.path bootstrap (5 lines):

```python
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
```

It ensures `import securagentx` / `import tools` / `import mcp` resolve to the
in-repo source tree even when pytest is invoked from a sub-directory or
against a pip-installed copy. No shared fixtures are defined here — each test
module defines its own fixtures (mostly `tmp_path`-based isolation plus
`unittest.mock.patch` of `securagentx.paths.SECURAGENTX_HOME` /
`SECURAGENTX_DIRS` to redirect persistent state to a temp dir).

#### `tests/brutal/conftest.py`

Mirrors the project-root conftest so `tests/brutal/` can be run in isolation
without losing the sys.path bootstrap.

#### `tests/_pkg_helper.py`

Helper that discovers the actual in-repo package directory by globbing for
`secur*` under the current working directory. Used by integration tests that
need to locate the package root dynamically (rather than hard-coding the
`securagentx` name).

### 6.7 CI Matrix

Two GitHub Actions workflows run on every push and pull request to `main`:

#### 6.7.1 `.github/workflows/ci.yml` — primary gate (Python matrix)

| Property | Value |
|:---------|:------|
| Trigger | `push` / `pull_request` on `main` |
| Runner | `ubuntu-latest` |
| Matrix | Python **3.11**, **3.12**, **3.13** |
| `fail-fast` | `false` (all matrix cells run to completion) |
| Install | `pip install -e .` + `pip install pytest pytest-timeout rich` |
| Test command | `python -m pytest -q --timeout=300 tests/ -m "not integration" --ignore=tests/test_brain_coverage.py --ignore=tests/test_brain_coverage_gap.py --tb=short` |
| Smoke test | `python -m securagentx --help || securagentx --help || true` |

The two `--ignore=` entries skip the deprecated brain-coverage modules that
are not part of the canonical VulnAgent code path.

#### 6.7.2 `.github/workflows/test.yml` — extended suite (Python 3.12)

| Property | Value |
|:---------|:------|
| Trigger | `push` / `pull_request` on `main` |
| Runner | `ubuntu-latest` |
| Timeout | 15 minutes |
| Python | `3.12` (pinned, with `pip` cache) |
| Install | `pip install -e .` + `pip install pytest pytest-timeout rich` |
| Unit step | `python -m pytest tests/ -v -m "not integration"` with `--ignore=` for 6 known-network-dependent modules (`test_orchestrator_modules.py`, `test_hunt_engine.py`, `test_integration_real.py`, `test_vulnerable_target_hunt.py`, `test_ecosystem.py`, `test_executor_freedom.py`, `test_cli_e2e.py`) |
| Integration step | `python -m pytest tests/ -v -m "integration"` with `continue-on-error: true` |

The two workflows are complementary: `ci.yml` enforces a Python-version matrix
gate, `test.yml` provides deeper verbose output and runs the integration
suite on a best-effort basis.

### 6.8 Coverage Requirements

SecurAgentX does not currently enforce a hard coverage threshold in CI —
neither workflow invokes `pytest --cov` with `--cov-fail-under`. Coverage is
monitored manually via the command in §6.4.6 and the generated `htmlcov/`
report.

The practical bar is:

- **All non-integration tests must pass** on Python 3.11, 3.12, and 3.13
  (the `ci.yml` matrix gate).
- **The 1,406 brutal tests must pass** — they are the de-facto coverage
  contract for the security-sensitive code paths (`securagentx.reports.*`,
  `securagentx.flows.*`, `securagentx.agent.*`, `securagentx.scope`,
  `securagentx.governance`, `securagentx.paths`).
- **Integration tests are advisory** — `continue-on-error: true` in
  `test.yml` means a flaky upstream API does not block merges, but
  regressions are still surfaced for review.

Future hardening: once the legacy `core/brain.py` coverage modules are
removed, a `--cov-fail-under=80` gate can be added to `ci.yml` without
disrupting the matrix.
