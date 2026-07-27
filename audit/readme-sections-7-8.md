## 7. Project Structure

SecurAgentX is organized as a single Python package (`securagentx/`) plus a set of sibling tool/agent/TUI directories that ship alongside the CLI entry point. Runtime artifacts (memory, skills, reports, logs) live under `~/.securagentx/` and are created on first run; only source and config are tracked in the repository.

### 7.1 Top-Level Layout

```text
SecurAgentX/
├── securagentx/          # Canonical Python package (the framework core)
├── tools/                # 100+ security tool modules (recon → exploit → report)
├── agents/               # Specialized agent roles & red-team captain/scanner/planner
├── mcp/                  # Model Context Protocol server, client, manager, config
├── commands/             # CLI command handlers (scan, mcp_runner, system, worldclass)
├── cli/                  # Rich UI components, wizard, textual TUI bridge
├── tui/                  # Textual TUI screens (dashboard, hunt view, findings, export)
├── core/                 # Legacy stubs (deprecated — preserved for import compat)
├── pipeline/             # Legacy scope.py only (old phase pipeline removed)
├── redteam_agent/        # Red-team agent entry point
├── prompts/              # AI system prompts, few-shot examples, vuln-finder prompts
├── knowledge/            # Methodology documentation (security playbook)
├── integrations/         # Telegram bot gateway & notification utilities
├── tests/                # 334-test suite + brutal/ integration stress tests
├── scripts/              # Logo generators, scan-check helper scripts
├── examples/             # Plugin examples (hello_world, ollama_local)
├── assets/               # Brand logo (PNG/SVG), dividers, typing animation
├── docs/                 # Design specs & implementation plans (compose/)
├── audit/                # Internal rename-audit reports (phase1-7)
├── main.py               # CLI entry point (`securagentx = "main:main"`)
├── pyproject.toml        # Build, deps, black/isort/flake8/pytest config
├── pytest.ini            # Legacy pytest config (testpaths, asyncio mode)
├── mcp.json.example      # Template for ~/.securagentx/mcp.json (auto-copied on first run)
├── config.yaml.example   # Template for ~/.securagentx/config.yaml
├── .env.example          # Template for ~/.securagentx/.env (API keys)
├── MEMORY.md.example     # Template for ~/.securagentx/MEMORY.md
├── apply_to_fork.sh      # Helper: apply patches to a fork
├── apply_to_fork_termux.sh  # Helper: apply patches to a Termux fork
├── LICENSE               # GPL-3.0-only full text
├── README.md             # This file
├── CONTRIBUTING.md       # Contribution guidelines
├── CODE_OF_CONDUCT.md    # Contributor Covenant 2.1
├── SECURITY.md           # Vulnerability disclosure policy
└── CHANGELOG.md          # Keep-a-Changelog history (1.0.0 — 2026-05-29)
```

### 7.2 `securagentx/` Package — Framework Core

```text
securagentx/
├── __init__.py              # Package marker, version export
├── __main__.py              # `python -m securagentx` entry
├── agent.py                 # Top-level agent facade (re-exports VulnAgent)
├── brain.py                 # Hybrid brain (DEPRECATED — kept for compat)
├── loop.py                  # Main agent reasoning loop (REASON → SELECT → EXECUTE → ADAPT)
├── paths.py                 # ~/.securagentx/ path resolution (memory, skills, reports, logs)
├── scope.py                 # Target validation & scope enforcement
├── governance.py            # Governance gate: SAFE / PRIVILEGED / DESTRUCTIVE classification
├── constitution.py          # Constitutional principles for agent behavior
├── constitution_engine.py   # Constitution evaluation engine
├── constants.py             # Shared constants (risk levels, exit codes, defaults)
├── types.py                 # Shared dataclasses & typed structures
├── memory.py                # Top-level memory facade (ChromaDB + FTS5 fallback)
│
├── agent/                   # VulnAgent — the true autonomous AI agent
│   ├── __init__.py          # Exports VulnAgent
│   ├── vuln_agent.py        # Main agent + 25-tool AVAILABLE_TOOLS registry
│   ├── agent_memory.py      # JSON-backed cross-session memory (memorize/recall/forget)
│   ├── agent_skills.py      # JSON-backed skill store (save_skill/recall_skill/list_skills)
│   ├── memory.py            # ChromaDB + SQLite FTS5 vector memory
│   └── report.py            # Finding report generation
│
├── agents/                  # Specialized agent roles (multi-agent collaboration)
│   ├── base.py              # BaseAgent abstract class
│   ├── primary_agent.py     # Orchestrating primary agent
│   ├── pentester.py         # Penetration-testing specialist
│   ├── coder.py             # Code-generation agent
│   ├── refiner.py           # Output refinement agent
│   ├── generator.py         # Payload/exploit generator
│   ├── reporter.py          # Report-writer agent
│   ├── reflector.py         # Self-reflection / critique agent
│   ├── enricher.py          # Finding enrichment agent
│   ├── installer.py         # Tool-installer agent (within governance)
│   ├── summarizer.py        # Conversation summarizer
│   ├── assistant.py         # General assistant
│   ├── adviser.py           # Strategic adviser
│   ├── memorist.py          # Memory-curation agent
│   ├── searcher.py          # Web/intelligence searcher
│   └── toolcall_fixer.py    # Self-healing broken tool calls
│
├── api/                     # FastAPI REST + GraphQL surface
│   ├── app.py               # FastAPI app factory
│   ├── _models.py           # Pydantic request/response models
│   ├── _auth.py             # Auth dependency wiring
│   └── routes/              # Route modules: auth, health, flows, providers, tokens, knowledge
│
├── auth/                    # Authentication subsystem
│   ├── oauth.py             # OAuth2 flows
│   ├── tokens.py            # Token issuance & validation
│   ├── sessions.py          # Session management
│   ├── middleware.py        # Auth middleware
│   └── models.py            # User/Session models
│
├── docker/                  # Sandbox & Docker lifecycle (agent execution isolation)
│   ├── sandbox.py           # Sandbox entry point
│   ├── lifecycle.py         # Container start/stop
│   ├── image_chooser.py     # Image selection per task
│   ├── network.py           # Network isolation
│   ├── resource_limits.py   # CPU/memory caps
│   ├── cleanup.py           # Container teardown
│   ├── file_ops.py          # File I/O between host & container
│   ├── terminal.py          # Pseudo-terminal bridge
│   ├── browser.py           # Headless browser in container
│   └── db.py                # Container-state DB
│
├── flows/                   # Multi-step flow orchestration (Flow → Task → Subtask)
│   ├── manager.py           # Flow lifecycle manager
│   ├── models.py            # Flow/Task/Subtask dataclasses
│   ├── state_machine.py     # State transitions
│   ├── flow_worker.py       # Flow-level worker
│   ├── task_worker.py       # Task-level worker
│   ├── subtask_worker.py    # Subtask-level worker
│   └── db.py                # Flow persistence (aiosqlite)
│
├── graphql/                 # GraphQL schema (queries, mutations, subscriptions, types)
│   ├── schema.py            # Root schema
│   ├── queries.py           # Read operations
│   ├── mutations.py         # Write operations
│   ├── subscriptions.py     # Live updates
│   └── types.py             # GraphQL types
│
├── knowledge_graph/         # Local Graphiti-style knowledge graph (networkx)
│   ├── graph.py             # Graph data structure
│   ├── extractor.py         # Entity/relation extraction
│   ├── community.py         # Community detection
│   └── integration.py       # Integration with agent memory
│
├── observability/           # Telemetry & tracing
│   ├── metrics.py           # Counter/histogram metrics
│   ├── otel.py              # OpenTelemetry exporter
│   ├── langfuse.py          # Langfuse trace exporter
│   ├── chains.py            # Chain-level tracing wrappers
│   └── logging.py           # Structured logging config
│
├── providers/               # LLM provider adapters (provider-agnostic client)
│   ├── base.py              # BaseProvider abstract class
│   ├── registry.py          # Provider registry & lookup
│   ├── _openai_compat.py    # Shared OpenAI-compatible HTTP helpers
│   ├── openai.py            # OpenAI
│   ├── anthropic.py         # Anthropic Claude
│   ├── gemini.py            # Google Gemini
│   ├── deepseek.py          # DeepSeek
│   ├── ollama.py            # Ollama (local)
│   ├── groq.py / bedrock.py # Groq / AWS Bedrock (via _openai_compat)
│   ├── glm.py / kimi.py / qwen.py  # GLM / Kimi / Qwen (via _openai_compat)
│   └── custom.py            # User-defined custom provider
│
├── scanning/                # Scanning subsystems (specialist agents, planner, critic)
│   ├── scan_loop.py         # Top-level scan loop
│   ├── scan_context.py      # Per-scan context object
│   ├── planner.py           # Attack-tree planner
│   ├── strategist.py        # Strategy selection
│   ├── specialist.py        # Per-domain specialist
│   ├── critic.py            # Self-critique before action
│   ├── executor.py          # Tool execution dispatcher
│   ├── decision_engine.py   # Decision routing
│   ├── worker.py            # Background worker
│   ├── universal.py         # Universal scan path
│   ├── hybrid_agent.py      # Hybrid AI + script agent
│   ├── hybrid_prompts.py    # Prompt templates for hybrid mode
│   ├── hypothesis_boost.py  # Hypothesis generation & ranking
│   ├── vuln_reasoning_phase.py  # Vulnerability reasoning phase
│   ├── post_processor.py    # Finding post-processing
│   ├── prompt_builder.py    # Prompt assembly
│   ├── conversation.py      # Multi-turn conversation state
│   ├── intent.py            # User-intent classification
│   ├── modes.py             # CHILL / HUNT operational modes
│   ├── dataclasses.py       # Scan dataclasses
│   ├── helpers.py           # Shared helpers
│   ├── logger.py            # Scan logger
│   ├── agent_council.py     # Multi-agent council
│   └── tui_game.py          # Gamified TUI overlay
│
├── search_providers/        # Web-search backends (DuckDuckGo, Google, SearXNG, ...)
│   ├── base.py / registry.py  # Base class & registry
│   ├── duckduckgo.py / google.py / searxng.py
│   ├── tavily.py / perplexity.py / traversaal.py  # API-keyed search engines
│   └── sploitus.py          # Exploit-db search
│
└── tools/                   # Package init re-exporting tool registry
    └── __init__.py
```

### 7.3 `tools/` — Security Tool Modules (Categorized)

The `tools/` directory holds 100+ standalone tool modules that VulnAgent selects from at runtime. They are grouped below by phase; most modules are self-contained Python files importing only stdlib + project utils.

```text
tools/
│
├── Reconnaissance
│   ├── base_recon.py             # Abstract recon base
│   ├── python_recon.py           # Pure-Python recon (no external Go deps)
│   ├── smart_recon.py            # LLM-guided recon planner
│   ├── endpoint_discovery.py     # Content/endpoint brute
│   ├── api_finder.py             # API surface discovery
│   ├── dork_miner.py             # Google-dork mining
│   ├── wayback_tool.py           # Wayback Machine history
│   ├── github_intel.py           # GitHub dorking / repo intel
│   ├── threat_intel.py           # Threat-intel feeds
│   ├── cve_database.py           # Local CVE lookup
│   ├── nvd_cve.py                # NVD CVE enrichment
│   ├── vulncheck_tool.py         # VulnCheck integration
│   ├── supply_chain_analyzer.py  # Dependency confusion / typosquat
│   ├── file_relationship_mapper.py  # File-to-file impact graph
│   ├── js_analyzer.py            # JS file reverse-engineering
│   └── api_schema_diff.py        # API schema drift detection
│
├── Exploit / Vulnerability Testing
│   ├── exploitation.py           # Generic exploitation harness
│   ├── bola_tester.py            # Broken Object Level Auth (BOLA/IDOR)
│   ├── bola_harness.py           # BOLA test orchestration
│   ├── jwt_tester.py             # JWT confusion / alg-none / key confusion
│   ├── ssti_scanner.py           # Server-Side Template Injection
│   ├── injection_tester.py       # SQLi / command / LDAP injection
│   ├── ssrf_scanner.py           # Server-Side Request Forgery
│   ├── xxe_scanner.py            # XML External Entity
│   ├── graphql_scanner.py        # GraphQL introspection / batching / injection
│   ├── deserialization_scanner.py  # Insecure deserialization
│   ├── race_condition_tester.py  # TOCTOU race conditions
│   ├── subdomain_takeover.py     # DNS / CNAME takeover
│   ├── targeted_attacks.py       # Targeted payload chains
│   ├── exploit_template.py       # Exploit template generator
│   ├── exploit_chain_builder.py  # Multi-step exploit chains
│   ├── escalation_engine.py      # Privilege escalation paths
│   ├── access_control_matrix.py  # RBAC/ABAC matrix tester
│   ├── auth_tester.py            # Auth bypass / brute / session
│   ├── auth_session.py           # Session fixation / hijack
│   ├── cors_checker.py           # CORS misconfiguration
│   ├── mobile_api_tester.py      # Mobile-specific API testing
│   ├── active_fuzzer.py          # Active fuzzing engine
│   ├── workflow_fuzzer.py        # Stateful workflow fuzzer
│   ├── payload_mutation.py       # Payload mutation library
│   ├── dynamic_waf_mutator.py    # WAF-evading payload mutator
│   ├── waf_evasion.py            # WAF bypass techniques
│   ├── waf_detector.py           # WAF fingerprinting
│   ├── waf_signatures.py         # WAF signature DB
│   ├── arjun_integration.py      # Parameter discovery (Arjun)
│   ├── param_miner.py            # Hidden parameter mining
│   ├── edr_evasion.py            # EDR/AV evasion (within scope)
│   ├── sast_engine.py            # Static analysis (Py/JS/Go/Java/PHP)
│   ├── cloud_scanner.py          # Cloud / IaC scanner (TF/AWS/GCP/Azure)
│   ├── zero_day_heuristics.py    # Zero-day heuristic patterns
│   ├── logic_flaw_engine.py      # Business-logic flaw detection
│   ├── logic_analyzer.py         # Logic-flow analysis
│   ├── base_scanner.py           # Abstract scanner base
│   ├── native_scanner.py         # Native (no-dep) scanner
│   ├── smart_scanner.py          # LLM-guided scanner
│   ├── omni_scan.py              # Omni-mode composite scanner
│   ├── vuln_engine.py            # Vuln dispatch engine
│   ├── vuln_finder.py            # Vuln-finding agent bridge
│   ├── vuln_hunter_core.py       # Vuln-hunt core loop
│   ├── vuln_reasoning.py         # Chain-of-thought vuln reasoning
│   ├── vuln_researcher.py        # Vulnerability research agent
│   └── vuln_knowledge.py         # Vuln knowledge base
│
├── Post-Exploitation & Persistence
│   ├── session_manager.py        # Session save / load / resume
│   ├── token_manager.py          # Token lifecycle management
│   ├── token_counter.py          # LLM token counting (tiktoken)
│   ├── mission_state.py          # Mission state persistence
│   ├── history_manager.py        # Hunt history persistence
│   ├── learning_engine.py        # Cross-session learning
│   ├── memory_manager.py         # Memory store manager
│   ├── memory_persistence.py     # Memory persistence layer
│   ├── memory_profile.py         # Memory profiling helper
│   ├── vector_memory.py          # ChromaDB vector memory ops
│   ├── user_memory.py            # Per-user memory partitioning
│   ├── finding_dedup.py          # Finding de-duplication
│   ├── finding_provenance.py     # Finding provenance tracking
│   ├── coverage_analyzer.py      # Test-coverage analyzer
│   ├── ml_filter.py              # ML false-positive filter
│   ├── verification_engine.py    # Finding verification
│   ├── profile_manager.py        # Target profile manager
│   ├── user_preferences.py       # User preference store
│   └── agent_reflection.py       # Post-run self-reflection
│
└── Reporting & Intelligence
    ├── reporter.py               # Core report generator
    ├── html_reporter.py          # HTML report writer
    ├── pdf_report_generator.py   # PDF report writer
    ├── bounty_reporter.py        # Bug-bounty formatted report
    ├── report_gen.py             # Generic report dispatcher
    ├── cvss_calculator.py        # CVSS v3.1 score calculator
    ├── soc_analyzer.py           # SOC-friendly finding triage
    ├── compliance_engine.py      # Compliance mapping (PCI/HIPAA/ISO)
    ├── enterprise_security.py    # Enterprise finding rollup
    ├── bounty_intelligence.py    # Bounty program intel
    ├── bounty_predictor.py       # Bounty payout predictor
    ├── progress_display.py       # Live progress UI
    ├── tui_dashboard.py          # TUI dashboard widget
    ├── dashboard_server.py       # Web dashboard server
    ├── interactive_dashboard.py  # Interactive dashboard
    ├── protocol_analyzer.py      # Protocol-level analysis
    ├── ecosystem.py              # Ecosystem / partner integrations
    ├── marketplace.py            # Plugin marketplace
    ├── telegram_bridge.py        # Telegram notification bridge
    ├── knowledge_graph.py        # KG visualization
    ├── tool_registry.py          # Tool registration catalog
    ├── tool_recommender.py       # LLM tool recommender
    ├── skill_registry.py         # Skill catalog
    └── api_reference.md          # Inline API reference doc
```

> **Note** — Additional `tools/` files (`ai_tool_creator.py`, `ai_sandbox.py`, `autonomous_agent.py`, `multi_agent.py`, `swarm_controller.py`, `multimodal_agent.py`, `llm_reasoning.py`, `universal_ai_client.py`, `universal_executor.py`, `command_suggest.py`, `adaptive_planner.py`, `agent_bola_bridge.py`, `chaining_engine.py`, `context_compressor.py`, `analysis_pipeline.py`, `hunt_engine.py`, `event_loop.py`, `dependency_manager.py`, `doctor.py`, `install_request.py`, `perf.py`, `updater.py`, `welcome_wizard.py`, `config_wizard.py`, `overlay_menu.py`, `research_tool.py`, `truffle_integration.py`) provide AI/agent orchestration, dependency & lifecycle management, and wizard flows — they are not phase-specific and are shared across recon/exploit/post-exploit/reporting.

### 7.4 `tests/` — Test Organization

```text
tests/
├── conftest.py                  # Shared pytest fixtures (sys.path setup, mocks)
├── _pkg_helper.py               # Import-path helper for in-tree packages
├── API_REFERENCE.md             # Inline API testing reference
│
├── (unit tests — top-level)
│   ├── test_brain.py / test_brain_coverage.py / test_brain_coverage_gap.py
│   ├── test_agent_brain_coverage.py
│   ├── test_vuln_agent.py / test_agent_tools.py / test_agent_agent_skills.py
│   ├── test_loop.py
│   ├── test_constitution_engine.py
│   ├── test_core_orchestrator.py
│   ├── test_securagentx_paths.py / test_securagentx_scope.py
│   ├── test_securagentx_governance.py / test_securagentx_agent_memory.py
│   ├── test_command_mcp_runner.py
│   ├── test_mcp_client.py / test_mcp_config.py / test_mcp_manager.py
│   ├── test_mcp_protocol.py / test_mcp_server.py
│   ├── test_tools_tool_recommender.py / test_tools_vuln_knowledge.py
│   ├── test_tools_safe_exec_retry.py / test_tools_data_facility.py
│   └── test_tools_vuln_reasoning_cot.py
│
├── test_scanning_*.py           # Scanning-subsystem suite (20 files)
│   ├── test_scanning_decision_engine.py
│   ├── test_scanning_vuln_reasoning_phase.py
│   ├── test_scanning_hypothesis_boost.py
│   ├── test_scanning_strategist.py
│   ├── test_scanning_planner.py
│   ├── test_scanning_specialist.py
│   ├── test_scanning_post_processor.py
│   ├── test_scanning_conversation.py
│   ├── test_scanning_worker.py
│   ├── test_scanning_tui_game.py
│   ├── test_scanning_scan_context.py
│   ├── test_scanning_critic.py
│   ├── test_scanning_agent_council.py
│   ├── test_scanning_universal.py
│   ├── test_scanning_intent.py
│   ├── test_scanning_modes.py
│   ├── test_scanning_scan_loop.py
│   ├── test_scanning_helpers.py
│   ├── test_scanning_executor.py
│   └── test_scanning_prompt_builder.py
│
├── brutal/                      # Adversarial stress / integration tests
│   ├── conftest.py
│   ├── test_agents_brutal.py
│   ├── test_api_auth_brutal.py
│   ├── test_docker_brutal.py
│   ├── test_integration_security_brutal.py
│   └── test_kg_flows_providers_brutal.py
│
├── ssa/                         # Static-security-analysis test fixtures
│
└── vulnerable_target/
    └── app.py                   # Intentionally vulnerable Flask target (for live tests)
```

Run the suite with:

```bash
# Full suite
python3 -m pytest tests/ -v

# Stable, network-free subset
python3 -m pytest tests/test_tui.py tests/test_security.py tests/test_core_modules.py -v

# Brutal / integration stress tests (opt-in via marker)
python3 -m pytest tests/brutal/ -v
python3 -m pytest tests/ -m "not integration"   # skip network-hitting tests
```

### 7.5 Runtime Data (`~/.securagentx/`)

Created on first run; not tracked in the repository.

```text
~/.securagentx/
├── config.yaml        # Active configuration (copied from config.yaml.example)
├── .env               # API keys (NEVER commit)
├── mcp.json           # MCP server config (auto-copied from mcp.json.example)
├── MEMORY.md          # Editable long-form memory
└── data/
    ├── memory.json    # JSON cross-session memory store
    ├── skills.json    # JSON skill store (saved tool scripts)
    └── securagentx.db # SQLite/FTS5 fallback memory (when ChromaDB unavailable)
```

---

## 8. Contributing & License

SecurAgentX welcomes contributions from the open-source security community. This section covers the full contribution lifecycle — from fork to merged PR — plus the code-style, pre-commit, security, and licensing rules every contributor must follow.

### 8.1 How to Contribute

The contribution workflow is the standard fork → branch → PR model:

```text
1. Fork  https://github.com/moussa12345678/SecurAgentX  → your GitHub account
2. Clone your fork locally
3. Create a feature branch off `main`
4. Make changes (follow §8.3 code style + §8.4 pre-commit)
5. Run the test suite (§8.6)
6. Push to your fork
7. Open a Pull Request against moussa12345678/SecurAgentX:main
8. Address review feedback; a maintainer merges once CI is green
```

Branch naming convention: `<type>/<short-slug>` — e.g. `feat/jwt-confusion`, `fix/asyncio-crash`, `docs/contributing-rewrite`.

### 8.2 Development Setup

```bash
# 1. Clone your fork
git clone https://github.com/<your-username>/SecurAgentX.git
cd SecurAgentX

# 2. Add the upstream remote (for staying in sync)
git remote add upstream https://github.com/moussa12345678/SecurAgentX.git

# 3. Create & activate a virtual environment (Python ≥ 3.10)
python3 -m venv .venv
source .venv/bin/activate

# 4. Install the package in editable mode WITH dev extras
pip install --upgrade pip
pip install -e ".[dev]"

# 5. Install pre-commit hooks (§8.4)
pip install pre-commit
pre-commit install

# 6. Configure your API key (use any supported provider)
cp .env.example .env
echo "GEMINI_API_KEY=your-key-here" >> .env

# 7. Verify the install
securagentx doctor
python3 -m pytest tests/ -v
```

> **Editable install** — `pip install -e ".[dev]"` exposes the `securagentx` console script, installs `pytest`, `black`, `isort`, `flake8`, `mypy`, and `ruff`, and lets you edit source with live reload.

### 8.3 Code Style

Tooling is configured in `pyproject.toml`. All contributions must pass `black`, `isort`, and `flake8` with the project's settings.

| Tool     | Setting                                         | Source                     |
|----------|-------------------------------------------------|----------------------------|
| `black`  | `line-length = 100`, `target-version = ["py310"]` | `[tool.black]` in pyproject.toml |
| `isort`  | `profile = "black"`, `line_length = 100`, `known_first_party = ["tools","agents","tui","commands"]` | `[tool.isort]` |
| `flake8` | `max-line-length = 100`, `ignore = ["E501","W503","E203"]`, `exclude = ["venv","__pycache__",".git"]` | `[tool.flake8]` |
| `ruff`   | Included in `dev` extras (subset of flake8 rules) | `[project.optional-dependencies]` |
| `mypy`   | Included in `dev` extras (strict recommended)    | `[project.optional-dependencies]` |

Run locally:

```bash
black --check --line-length 100 .
isort --check-only --profile black .
flake8 .
mypy securagentx
```

**Core style rules (from `CONTRIBUTING.md`):**

- **Python 3.10+** required (use `from __future__ import annotations` for forward refs).
- **4-space indentation** everywhere — no tabs, no 2-space.
- **Type hints** on every public function and method.
- **Docstrings** on every module, class, and public function (Google style preferred).
- **No emoji** in terminal output, log messages, or comments. Use text markers: `[OK]`, `[FAIL]`, `[WARN]`, `[INFO]`, `[RUN]`, `[SKIP]`.
- **Use `rich`** for all terminal UI (panels, tables, spinners); import shared components from `cli/ui_components.py` rather than instantiating your own `Console()`.
- **Logging** via `logging.getLogger("securagentx.module_name")` with structured messages.

**Security rules (non-negotiable):**

- **Never use `shell=True`** in `subprocess` calls — always pass list-form arguments.
- **Always validate targets** through `securagentx.scope` before dispatching to external tools.
- **Never store API keys** in `config.yaml` — use `.env` only.
- **Sanitize all user input** before any shell interaction.
- **Shell commands are only allowed behind the Governance layer** (SAFE / PRIVILEGED / DESTRUCTIVE classification).

**Commit message format** (Conventional Commits):

```text
fix: resolve asyncio crash in llm_client
feat: add gau and ffuf to dependency manager
docs: update CONTRIBUTING with code standards
refactor: extract command handlers from main.py
test: add BOLA tester brutal suite
chore: bump black to 23.3.0
```

### 8.4 Pre-Commit Hooks

Pre-commit is configured in `.pre-commit-config.yaml` and runs the following hooks on every commit:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - trailing-whitespace      # strip trailing whitespace
      - end-of-file-fixer        # ensure newline at EOF
      - check-yaml               # validate YAML syntax
      - check-added-large-files  # block accidental binary commits
      - check-merge-conflict     # block unresolved conflict markers

  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        language_version: python3.12
        args: [--line-length=100]
```

Install once after cloning:

```bash
pip install pre-commit
pre-commit install      # hooks into .git/hooks/pre-commit
pre-commit run --all-files   # run manually across the whole repo
```

> Commits that fail any hook are aborted. Fix the reported issues and re-stage.

### 8.5 Pull Request Process

1. **Open the PR** against `moussa12345678/SecurAgentX:main` from your feature branch.
2. **Fill in the PR template** (`.github/PULL_REQUEST_TEMPLATE.md`): description, type-of-change checklist, testing checklist, and the project-style checklist (4-space indent, type hints, docstrings, no `shell=True`, no secrets, `ui_components` imports).
3. **CI must pass** — GitHub Actions runs the test suite across a Python 3.11/3.12/3.13 matrix (`.github/workflows/ci.yml`) plus a single-version lint/test workflow (`.github/workflows/test.yml`).
4. **Brutal tests** (`tests/brutal/`) must pass for any change touching `securagentx/`, `agents/`, `tools/`, or `mcp/`.
5. **Request review** from a maintainer. Address feedback by pushing new commits (do not force-push after review starts unless asked).
6. **Squash-merge** is the default; the maintainer will squash your branch into a single commit on `main` using your PR title as the commit message.
7. **CHANGELOG.md** — for user-facing changes, add an entry under the appropriate `[Unreleased]` section (or create one) following the [Keep a Changelog](https://keepachangelog.com/) format.

### 8.6 Testing

```bash
# Full suite (334 tests)
python3 -m pytest tests/ -v

# Single file
python3 -m pytest tests/test_security.py -v

# Skip network-hitting integration tests
python3 -m pytest tests/ -m "not integration" -v

# Brutal / adversarial stress tests
python3 -m pytest tests/brutal/ -v
```

Pytest is configured in `pyproject.toml` under `[tool.pytest.ini_options]`:
- `testpaths = ["tests"]`
- `asyncio_mode = "auto"` (pytest-asyncio)
- `markers = ["integration: opt-in integration tests that hit real network/services"]`

### 8.7 Configuration Files

| File                  | Purpose                              | Tracked? |
|-----------------------|--------------------------------------|:--------:|
| `config.yaml.example` | Template — copied to `~/.securagentx/config.yaml` | Yes |
| `config.yaml`         | Active configuration (no secrets)    | No       |
| `.env.example`        | Template for API keys                | Yes      |
| `.env`                | Actual API keys                      | No       |
| `mcp.json.example`    | MCP server config template           | Yes      |
| `~/.securagentx/mcp.json` | User MCP config (overrides project) | No    |

### 8.8 Code of Conduct (Summary)

SecurAgentX adopts the [Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating you agree to keep the community **harassment-free for everyone**, regardless of age, body size, disability, ethnicity, sex characteristics, gender identity and expression, experience level, education, socio-economic status, nationality, appearance, race, caste, color, religion, or sexual orientation.

- **Expected**: welcoming language, respect for differing viewpoints, constructive criticism, empathy.
- **Unacceptable**: sexualized language or advances, trolling, insults, personal/political attacks, harassment, publishing others' private information.
- **Enforcement**: report violations to **AAAAAACD@proton.me** — all complaints reviewed promptly and fairly.
- **Full text**: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

### 8.9 Security Policy (Summary)

SecurAgentX is itself a security tool. If you discover a vulnerability **in SecurAgentX itself** (not findings from using it against a target), report it responsibly.

- **Do NOT open a public GitHub issue** for security vulnerabilities.
- **Email**: **AAAAAACD@proton.me** with: description, reproduction steps, impact assessment, suggested fix (if any).
- **Response timeline**: acknowledgment within 48 h, initial assessment within 5 business days, patch release within 14 business days.
- **In scope**: command injection via agent inputs, governance bypass (DESTRUCTIVE execution), API-key leakage via logs/outputs, arbitrary file read/write outside designated directories, privilege escalation in the agent execution context.
- **Out of scope**: vulnerabilities in third-party Go tools (subfinder, nuclei, etc.), issues requiring physical access, social-engineering attacks.
- **Supported versions**: latest `main` only; older releases are not supported.

SecurAgentX enforces defense-in-depth: **Governance Gate** (SAFE/PRIVILEGED/DESTRUCTIVE) → **no `shell=True`** → **metacharacter blocking** (`| ; ` ` $()`) → **target validation** → **scope enforcement**. Full text: [`SECURITY.md`](SECURITY.md).

### 8.10 License

SecurAgentX is released under the **GNU General Public License v3.0 only** (**GPL-3.0-only**).

- **SPDX identifier**: `GPL-3.0-only`
- **Full text**: [`LICENSE`](LICENSE) (GNU GPL v3, 29 June 2007)
- **Copyright**: © 2026 [SecurAgentX Project](https://github.com/moussa12345678/SecurAgentX) / moussa12345678
- **pyproject.toml declaration**: `license = {text = "GPL-3.0-only"}`
- **Classifier**: `License :: OSI Approved :: GNU General Public License v3 (GPLv3)`

By contributing to SecurAgentX, you agree that your contributions will be licensed under the same GPL-3.0-only terms. No CLA is required; the inbound=outbound model applies.

> **Built for the open-source security community.** — [![GitHub Stars](https://img.shields.io/github/stars/moussa12345678/SecurAgentX?style=for-the-badge&color=red)](https://github.com/moussa12345678/SecurAgentX)
