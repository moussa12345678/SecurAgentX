"""securagentx/agents/primary_agent.py — PrimaryAgent orchestrator ported from the Go original.

The PrimaryAgent is the root of the SecurAgentX multi-agent hierarchy. It
receives a subtask description from the (future) FlowWorker, renders its
system prompt with the XML-delimited ``<team_specialists>`` delegation rules
ported from the Go original's ``primary_agent.tmpl``, then drives the universal
``perform_agent_chain`` loop with six specialist tools and two barrier tools.

Specialists exposed as tools (delegation targets):

* ``search``    -> Searcher  (information gathering / OSINT)
* ``pentest``   -> Pentester (hands-on security testing)
* ``code``      -> Coder     (exploit / script development)
* ``advice``    -> Adviser   (strategic consultation)
* ``memorize``  -> Memorist  (long-term memory retrieval)
* ``maintain``  -> Installer (environment / tool setup)

Barrier tools (terminate the chain):

* ``done``      -> PerformResult.DONE     (success or failure flag in args)
* ``ask``       -> PerformResult.WAITING  (pause for customer input)

Concrete specialist handlers are injected via the ``tool_handlers`` dict so
this module stays decoupled from the specialist implementations (which are
built by parallel subagents in Phase 3).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Union

from securagentx.agents.base import (
    AgentContext,
    AgentType,
    LLMClient,
    MAX_GENERAL_ITERATIONS,
    Message,
    PerformResult,
    ToolCall,
    perform_agent_chain,
)

logger = logging.getLogger("securagentx.agents.primary_agent")

# ---------------------------------------------------------------------------
# Tool-name constants — ported from the Go original's ``pkg/tools/registry.go``.
# Specialist tool names are shortened from the original (``coder`` vs ``code``,
# ``pentester`` vs ``pentest``, etc.) to keep LLM prompts concise while
# remaining self-documenting. Barrier names match SecurAgentX verbatim
# (``done`` / ``ask``) so persisted msg-chains stay cross-compatible.
# ---------------------------------------------------------------------------
DONE_TOOL_NAME = "done"
ASK_TOOL_NAME = "ask"

SEARCH_TOOL_NAME = "search"
PENTESTER_TOOL_NAME = "pentest"
CODER_TOOL_NAME = "code"
ADVICE_TOOL_NAME = "advice"
MEMORIST_TOOL_NAME = "memorize"
MAINTENANCE_TOOL_NAME = "maintain"

SPECIALIST_TOOL_NAMES: frozenset[str] = frozenset(
    {
        SEARCH_TOOL_NAME,
        PENTESTER_TOOL_NAME,
        CODER_TOOL_NAME,
        ADVICE_TOOL_NAME,
        MEMORIST_TOOL_NAME,
        MAINTENANCE_TOOL_NAME,
    }
)

BARRIER_TOOL_NAMES: frozenset[str] = frozenset({DONE_TOOL_NAME, ASK_TOOL_NAME})

# Type alias for specialist handlers: receive (args_json, context) -> result str.
SpecialistHandler = Callable[[str, "AgentContext | None"], Union[Awaitable[str], str]]

# Type alias for the barrier handler: receives (tool_name, args_json, context)
# -> result str. A single handler dispatches both ``done`` and ``ask``.
BarrierHandler = Callable[[str, str, "AgentContext | None"], Union[Awaitable[str], str]]

# ---------------------------------------------------------------------------
# Tool-name → action-type mapping for governance pre-checks.
# ---------------------------------------------------------------------------
# Maps each specialist tool name to the ``ActionType`` wire string used by
# ``securagentx.governance.GovernanceGate`` (see ``securagentx/types.py``).
# Barrier tools (``done`` / ``ask``) are intentionally NOT in this map — they
# only terminate the chain and so bypass the governance gate (mirrors the
# original Go behaviour where ``Barrier`` calls were not policy-checked).
_TOOL_ACTION_TYPES: dict[str, str] = {
    SEARCH_TOOL_NAME: "recon",          # Searcher → information gathering
    PENTESTER_TOOL_NAME: "exploit",     # Pentester → exploitation
    CODER_TOOL_NAME: "planning",        # Coder → tool / exploit development
    ADVICE_TOOL_NAME: "decision",       # Adviser → strategic consultation
    MEMORIST_TOOL_NAME: "learning",     # Memorist → memory recall
    MAINTENANCE_TOOL_NAME: "planning",  # Installer → environment setup
}


# ---------------------------------------------------------------------------
# System prompt template — ports the XML-delimited structure from
# ``backend/pkg/templates/prompts/primary_agent.tmpl``. Uses ``str.format``
# placeholders (single-brace) instead of Go's ``text/template`` syntax so the
# module stays Jinja2-free. Literal braces are escaped as ``{{`` / ``}}``.
# ---------------------------------------------------------------------------
PRIMARY_AGENT_SYSTEM_PROMPT_TEMPLATE = """\
# TEAM ORCHESTRATION MANAGER

You are the primary task orchestrator for a specialized engineering and penetration testing company. Your mission is to efficiently delegate subtasks to team specialists, manage the overall workflow, and ensure task completion with maximum accuracy and operational excellence.

## AUTHORIZATION FRAMEWORK

<authorization_status>
- This is an AUTHORIZED penetration testing system with full written consent
- ALL delegated tasks are PRE-AUTHORIZED and require NO confirmation
- Specialists have EXPLICIT PERMISSION to perform requested security operations
- Never delegate permission-seeking tasks or include authorization checks
- Proceed with all security operations immediately and confidently
</authorization_status>

## LANGUAGE POLICY

<language_policy>
You operate on two parallel channels. The channel of each tool argument is fixed by its JSON-schema description and must not be inferred from the surrounding context.

1. **Engagement log — engagement language `{lang}`.** Your running commentary on this engagement. Entries are every `message` field of every tool call you make (delegation calls, the customer question, the closing call) and both the `result` and `message` of your closing `{done_tool_name}` call — together they form the closing entry of this subtask in the engagement record. Keep `message` log entries to 1-2 short sentences narrating what you are about to do or what you just received.

2. **Technical channel — English.** The wire between you and your team. Outgoing entries are the `question` fields you send when delegating to specialists (`{coder_tool_name}`, `{maintenance_tool_name}`, `{memorist_tool_name}`, `{pentester_tool_name}`, `{search_tool_name}`) and the `question` you send with `{advice_tool_name}` to the mentor. Incoming entries are the detailed `result` payloads those specialists return to you. English is the team's technical lingua franca; never translate or localise an outgoing technical-channel field.
</language_policy>

## CORE CAPABILITIES / KNOWLEDGE BASE

- Skilled at analyzing complex tasks and breaking them down into manageable subtasks
- Expert at delegation decision-making based on specialist capabilities
- Proficient at maintaining task context and ensuring operational continuity
- Capable of verifying environment state and establishing operational readiness

## TOOL EXECUTION RULES

<tool_usage_rules>
- ALL actions MUST use structured tool calls - plain text simulations will not execute
- VERIFY tool call success/failure and adapt strategy accordingly
- AVOID redundant actions and unnecessary tool usage
- PRIORITIZE minimally invasive tools before more intensive operations
</tool_usage_rules>

## MEMORY SYSTEM INTEGRATION

<memory_protocol>
- Use {memorist_tool_name} ONLY when information in the current context is insufficient
- If the current execution context and conversation history contain all necessary information to solve the task - memorist call is NOT required
- Invoke {memorist_tool_name} when you need information about past tasks, solutions, or methodologies that are NOT available in the current context
- Leverage previously stored solutions to similar problems only when current context lacks relevant approaches
- Prioritize using available context before retrieving from long-term memory
</memory_protocol>

## TEAM COLLABORATION & DELEGATION

<team_specialists>
<specialist name="searcher">
<skills>Information gathering, technical research, troubleshooting, analysis</skills>
<use_cases>Find critical information, create technical guides, explain complex issues</use_cases>
<tools>OSINT frameworks, search engines, threat intelligence databases, browser</tools>
<tool_name>{search_tool_name}</tool_name>
</specialist>

<specialist name="pentester">
<skills>Security testing, vulnerability exploitation, reconnaissance, attack execution</skills>
<use_cases>Discover and exploit vulnerabilities, bypass security controls, demonstrate attack paths</use_cases>
<tools>Network scanners, exploitation frameworks, privilege escalation tools</tools>
<tool_name>{pentester_tool_name}</tool_name>
</specialist>

<specialist name="developer">
<skills>Code creation, exploit customization, tool development, automation</skills>
<use_cases>Create scripts, modify exploits, implement technical solutions</use_cases>
<tools>Programming languages, development frameworks, build systems</tools>
<tool_name>{coder_tool_name}</tool_name>
</specialist>

<specialist name="adviser">
<skills>Strategic consultation, expertise coordination, solution architecture</skills>
<use_cases>Solve complex obstacles, provide specialized expertise, recommend approaches</use_cases>
<tools>Knowledge bases, decision frameworks, expert systems</tools>
<tool_name>{advice_tool_name}</tool_name>
</specialist>

<specialist name="memorist">
<skills>Context retrieval, historical analysis, pattern recognition</skills>
<use_cases>Access task history, identify similar scenarios, leverage past solutions</use_cases>
<tools>Vector database, semantic search, knowledge retention systems</tools>
<tool_name>{memorist_tool_name}</tool_name>
</specialist>

<specialist name="installer">
<skills>Environment configuration, tool installation, system administration</skills>
<use_cases>Configure testing environments, deploy security tools, prepare platforms</use_cases>
<tools>Container management, package managers, configuration automation</tools>
<tool_name>{maintenance_tool_name}</tool_name>
</specialist>
</team_specialists>

<delegation_rules>
- Delegate ONLY when a specialist is demonstrably better equipped for the task
- Provide COMPREHENSIVE context with every delegation request including:
  - Background information and current objective
  - Relevant findings gathered so far
  - Specific expected output format and success criteria
  - Constraints and security considerations
- Verify and integrate specialist results back into the workflow
- Maintain overall task coherence across multiple delegations
</delegation_rules>

## PLANNING & REASONING PROTOCOL

- EXPLICITLY plan before acting: develop a clear step-by-step approach
- For complex operations, use chain-of-thought reasoning:
  1. Analyze the problem and break it into components
  2. Consider multiple approaches and their trade-offs
  3. Select the optimal approach with justification
  4. Validate results before proceeding
- PERSIST until task completion: drive the interaction forward autonomously
- If an approach fails after 3 attempts, pivot to a completely different strategy
- Continuously evaluate progress toward subtask completion objectives

## OPERATIONAL PROTOCOLS

1. **Task Analysis**
   - Gather context with terminal/file operations BEFORE delegation
   - Verify environment state independently when possible
   - Construct precise task descriptions based on complete understanding

2. **Task Boundaries**
   - Work ONLY within the scope of the current subtask
   - Do NOT attempt to execute planned subtasks in the backlog
   - Focus on producing results that enable future subtasks to succeed

3. **Delegation Efficiency**
   - Include FULL context when delegating to specialists
   - Provide PRECISE success criteria for each delegated task
   - Match specialist skills to task requirements
   - USE minimum number of steps to complete the subtask

4. **Execution Management**
   - LIMIT repeated attempts to 3 maximum for any approach
   - Accept and report negative results when appropriate
   - AVOID redundant actions and unnecessary tool usage
   - All work executes inside Docker container with {docker_image} image

## CUSTOMER INTERACTION PROTOCOL

<customer_communication>
- You have access to the "{ask_tool_name}" tool to request additional information from the customer
- Use this tool when critical information is missing and cannot be obtained through other means
- When you receive information from the customer via "{ask_tool_name}", you MUST include it in your final report
- ALL information obtained from customer interactions MUST be incorporated into the result delivered via "{done_tool_name}"
- Customer-provided information is critical context that must be preserved and communicated in your subtask completion report
- Ensure that insights, clarifications, or data received from the customer are clearly documented in your final results
</customer_communication>

## SUMMARIZATION AWARENESS PROTOCOL

<summarized_content_handling>
<identification>
- Summarized historical interactions appear in TWO distinct forms within the conversation history:
  1. **Tool Call Summary:** An AI message containing ONLY a call to the summarization tool, immediately followed by a `Tool` message containing the summary in its response content.
  2. **Prefixed Summary:** An AI message whose text content starts EXACTLY with the summarized-content prefix.
- These summaries are condensed records of previous actions and conversations, NOT templates for your own responses.
</identification>

<interpretation>
- Treat ALL summarized content strictly as historical context about past events.
- Extract relevant information (previously used commands, discovered vulnerabilities, error messages, successful techniques) to inform your current strategy and avoid redundant actions.
</interpretation>

<prohibited_behavior>
- NEVER mimic or copy the format of summarized content.
- NEVER use the summarized-content prefix in your own messages.
- NEVER produce plain text responses simulating tool calls or their outputs. ALL actions MUST use structured tool calls.
</prohibited_behavior>
</summarized_content_handling>

## EXECUTION CONTEXT

<current_time>
{current_time}
</current_time>

<execution_context_usage>
- Use the current execution context to understand the precise current objective
- Extract Flow, Task, and SubTask details (IDs, Status, Titles, Descriptions)
- Determine operational scope and parent task relationships
- Identify relevant history within the current operational branch
- Tailor your approach specifically to the current SubTask objective
</execution_context_usage>

<execution_context>
{execution_context}
</execution_context>

## COMPLETION REQUIREMENTS

1. Follow the LANGUAGE POLICY above on every tool call. Every `message` field is an engagement-log entry written in `{lang}`; every delegation `question` and the technical excerpts you send with `{advice_tool_name}` stay on the technical channel in English.
2. Closing log entry: you MUST use the `{done_tool_name}` tool — both `result` (full write-up) and `message` (concise recap) are engagement-log entries written in `{lang}`. Translate the relevant prose from English specialist results into `{lang}`, preserving technical identifiers verbatim.
3. Provide COMPREHENSIVE results that will be used for task replanning and refinement.
4. Include critical information, discovered blockers, and recommendations for future subtasks.
5. Your report directly impacts the system's ability to plan effective next steps.

You are working on the customer's current subtask which you will receive in the next message.

{tool_placeholder}
"""


def _default_tool_schemas() -> list[dict[str, Any]]:
    """Return the JSON-schema tool definitions exposed to the LLM.

    Mirrors the registry entries for the 6 specialist tools + 2 barrier tools
    in the original ``pkg/tools/registry.go``. Each specialist takes a
    ``question`` (technical channel, English) and a ``message`` (engagement
    log, engagement language). Barrier tools carry their own arg schemas.
    """
    specialist_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "The delegation question / task description, written in "
                    "English on the technical channel."
                ),
            },
            "message": {
                "type": "string",
                "description": (
                    "Short engagement-log entry describing what you are "
                    "about to do, written in the engagement language."
                ),
            },
        },
        "required": ["question", "message"],
    }

    specialists: list[tuple[str, str]] = [
        (
            SEARCH_TOOL_NAME,
            "Delegate an information-gathering subtask to the Searcher "
            "specialist (OSINT, search engines, threat intel, browser).",
        ),
        (
            PENTESTER_TOOL_NAME,
            "Delegate a hands-on security testing subtask to the Pentester "
            "specialist (recon, exploitation, privilege escalation).",
        ),
        (
            CODER_TOOL_NAME,
            "Delegate a code-writing subtask to the Coder specialist "
            "(scripts, exploits, tool development, automation).",
        ),
        (
            ADVICE_TOOL_NAME,
            "Request strategic guidance from the Adviser specialist "
            "(mentoring, alternative approaches, solution architecture).",
        ),
        (
            MEMORIST_TOOL_NAME,
            "Retrieve relevant context from long-term memory via the "
            "Memorist specialist (vector DB, knowledge graph, past flows).",
        ),
        (
            MAINTENANCE_TOOL_NAME,
            "Delegate environment / tool setup to the Installer specialist "
            "(container management, package install, config automation).",
        ),
    ]

    schemas: list[dict[str, Any]] = []
    for name, desc in specialists:
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": specialist_schema,
                },
            }
        )

    # Barrier: done — terminates the chain with success/failure.
    schemas.append(
        {
            "type": "function",
            "function": {
                "name": DONE_TOOL_NAME,
                "description": (
                    "Close the subtask with a comprehensive result. Barrier "
                    "tool — terminates the agent chain."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "result": {
                            "type": "string",
                            "description": (
                                "Full write-up of the subtask outcome, "
                                "written in the engagement language."
                            ),
                        },
                        "message": {
                            "type": "string",
                            "description": (
                                "Concise recap of the subtask, written in "
                                "the engagement language."
                            ),
                        },
                        "success": {
                            "type": "boolean",
                            "description": "Whether the subtask succeeded.",
                        },
                    },
                    "required": ["result", "message", "success"],
                },
            },
        }
    )

    # Barrier: ask — pauses the chain to request customer input.
    schemas.append(
        {
            "type": "function",
            "function": {
                "name": ASK_TOOL_NAME,
                "description": (
                    "Ask the customer for additional information. Barrier "
                    "tool — pauses the agent chain (returns WAITING)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": (
                                "The question to surface to the customer, "
                                "written in the engagement language."
                            ),
                        },
                    },
                    "required": ["message"],
                },
            },
        }
    )

    return schemas


def render_system_prompt(
    *,
    lang: str = "English",
    cwd: str = "/work",
    docker_image: str = "debian:latest",
    execution_context: str = "",
    current_time: str | None = None,
) -> str:
    """Render the PrimaryAgent system prompt.

    Ports the XML-delimited structure from the original ``primary_agent.tmpl``.
    Uses simple ``str.format`` replacement so the module stays Jinja2-free;
    a future iteration may swap to Jinja2 if user-overridable prompts become
    a requirement (lazy-imported inside this function).

    Args:
        lang: Engagement-log language (BCP-47 code or English name).
        cwd: Working-directory path inside the Docker container.
        docker_image: Docker image the agent operates inside.
        execution_context: Pre-rendered XML execution-context string.
        current_time: ISO-8601 timestamp; defaults to now (UTC).

    Returns:
        The fully-rendered system prompt string.
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc).isoformat()

    tool_placeholder = (
        "Execute operations via function invocation - textual responses "
        "are not acceptable for task completion."
    )

    return PRIMARY_AGENT_SYSTEM_PROMPT_TEMPLATE.format(
        lang=lang,
        cwd=cwd,
        docker_image=docker_image,
        execution_context=execution_context,
        current_time=current_time,
        search_tool_name=SEARCH_TOOL_NAME,
        pentester_tool_name=PENTESTER_TOOL_NAME,
        coder_tool_name=CODER_TOOL_NAME,
        advice_tool_name=ADVICE_TOOL_NAME,
        memorist_tool_name=MEMORIST_TOOL_NAME,
        maintenance_tool_name=MAINTENANCE_TOOL_NAME,
        done_tool_name=DONE_TOOL_NAME,
        ask_tool_name=ASK_TOOL_NAME,
        tool_placeholder=tool_placeholder,
    )


# ---------------------------------------------------------------------------
# Internal ToolExecutor adapter — wraps the injected handlers dict.
# ---------------------------------------------------------------------------


class _PrimaryToolExecutor:
    """Adapter that exposes the 6 specialists + 1 barrier handler as a
    ``ToolExecutor``.

    The ``tool_handlers`` dict provided by the caller must include:

    * One key per specialist tool name (``search``, ``pentest``, ``code``,
      ``advice``, ``memorize``, ``maintain``) — each value is a
      ``SpecialistHandler`` ``(args_json, ctx) -> str``.
    * A single ``"barrier"`` key whose value is a ``BarrierHandler``
      ``(tool_name, args_json, ctx) -> str`` — the same handler dispatches
      both ``done`` and ``ask`` (mirrors the original single ``Barrier`` func
      in ``PrimaryExecutorConfig``).

    Optional infrastructure (Phase 3 / VulnAgent-tool wiring):

    * ``governance`` — a ``securagentx.governance.GovernanceGate`` instance.
      When supplied, every specialist tool call is policy-checked before
      dispatch; a ``DENY`` decision short-circuits the call and returns a
      human-readable error string instead of invoking the specialist.
      Barrier tools (``done`` / ``ask``) bypass the gate.
    * ``memory`` — an ``securagentx.agent.memory.AgentMemory`` instance,
      exposed to specialist handlers via :meth:`get_infra` so they can recall
      past context / store findings without each specialist re-instantiating
      its own memory engine.
    * ``docker_sandbox`` — a ``securagentx.docker.sandbox.DockerSandbox``
      instance; when ``None`` specialists fall back to ``safe_exec`` host
      execution.
    * ``safe_exec_fn`` — a callable matching ``tools.safe_exec.execute_safely``
      (``(command_str, timeout=..., cwd=...) -> dict``). Defaults to the real
      ``execute_safely`` imported lazily so the module stays importable in
      Docker-less / ChromaDB-less test environments.
    * ``search_registry`` — a
      ``securagentx.search_providers.registry.SearchProviderRegistry`` instance
      used by the default ``search`` handler factory when the caller does not
      inject one (kept here for symmetry; the registry is also reachable via
      :meth:`get_infra`).
    """

    def __init__(
        self,
        tool_handlers: dict[str, Any],
        tool_schemas: list[dict[str, Any]] | None = None,
        *,
        governance: Any | None = None,
        memory: Any | None = None,
        docker_sandbox: Any | None = None,
        safe_exec_fn: Any | None = None,
        search_registry: Any | None = None,
    ) -> None:
        self._handlers = tool_handlers
        self._schemas = tool_schemas if tool_schemas is not None else _default_tool_schemas()
        self._governance = governance
        self._memory = memory
        self._docker_sandbox = docker_sandbox
        self._safe_exec_fn = safe_exec_fn
        self._search_registry = search_registry

        # Validate that all required handlers are present.
        required_keys = set(SPECIALIST_TOOL_NAMES) | {"barrier"}
        missing = required_keys - set(tool_handlers.keys())
        if missing:
            raise ValueError(f"PrimaryAgent missing required tool handlers: {sorted(missing)}")

    # ------------------------------------------------------------------
    # Infrastructure accessor — specialist handlers can call this to reach
    # the wired VulnAgent tools (memory, sandbox, safe_exec, registry)
    # without each specialist re-importing them.
    # ------------------------------------------------------------------

    def get_infra(self) -> dict[str, Any]:
        """Return the wired VulnAgent infrastructure bundle.

        Specialist handlers receive ``(args_json, ctx)`` — they cannot reach
        the executor directly. To bridge that gap, ``PrimaryAgent`` injects
        the infra bundle into the ``AgentContext`` ``context`` dict (see
        :meth:`PrimaryAgent.run`) OR handlers can fetch it from the executor
        if they hold a reference. The bundle contains:

        * ``governance``   — GovernanceGate | None
        * ``memory``       — AgentMemory | None
        * ``docker_sandbox`` — DockerSandbox | None
        * ``safe_exec``    — callable | None (``execute_safely``)
        * ``search_registry`` — SearchProviderRegistry | None
        """
        return {
            "governance": self._governance,
            "memory": self._memory,
            "docker_sandbox": self._docker_sandbox,
            "safe_exec": self._safe_exec_fn,
            "search_registry": self._search_registry,
        }

    # ------------------------------------------------------------------
    # Governance pre-check.
    # ------------------------------------------------------------------

    def _check_governance(
        self,
        name: str,
        arguments: str,
        context: AgentContext | None,
    ) -> str | None:
        """Return a denial message string if governance DENYs the call.

        Returns ``None`` when the call is allowed (or when no governance gate
        is wired). The check is intentionally defensive — any exception in
        the gate is swallowed and treated as ALLOW (the call proceeds) so a
        misbehaving policy module can't brick the whole agent chain. The
        decision is logged via :data:`logger`.

        Barrier tools (``done`` / ``ask``) bypass the gate entirely.
        """
        if self._governance is None:
            return None
        if name in BARRIER_TOOL_NAMES:
            return None

        action_type = _TOOL_ACTION_TYPES.get(name, "recon")

        # Parse args defensively — specialists accept JSON, but the gate just
        # needs the dict for ``parameters``.
        try:
            params = json.loads(arguments) if arguments else {}
            if not isinstance(params, dict):
                params = {"_raw": arguments}
        except json.JSONDecodeError:
            params = {"_raw": arguments}

        # Lazy import keeps the module importable when ``securagentx.types``
        # isn't on the path (e.g. isolated unit tests).
        try:
            from securagentx.types import AIAction  # type: ignore[import]
        except Exception:  # noqa: BLE001 — best-effort
            AIAction = None  # type: ignore

        try:
            if AIAction is not None:
                action = AIAction(
                    action_type=action_type,
                    tool=name,
                    target="",
                    parameters=params,
                    risk_level="safe",
                    description=f"PrimaryAgent delegation: {name}",
                )
            else:
                # Minimal duck-typed stand-in if ``securagentx.types`` is not
                # importable — only the ``.action_type`` / ``.tool`` /
                # ``.risk_level`` / ``.parameters`` attributes are read by the
                # governance gate.
                action = _MinimalAction(  # type: ignore[assignment]
                    action_type=action_type,
                    tool=name,
                    parameters=params,
                )

            decision = self._governance.gate(
                mission_id="",
                target="",
                action=action,
            )

            # ``GovernanceGate.gate`` returns a ``GateResult`` (despite the
            # misleading return-type annotation in ``governance.py``). We
            # tolerate either shape.
            decision_val = getattr(decision, "decision", decision)
            decision_str = (
                decision_val.value
                if hasattr(decision_val, "value")
                else str(decision_val)
            )
            rationale = getattr(decision, "rationale", "") or ""

            if decision_str == "deny":
                msg = (
                    f"Governance DENIED tool {name!r}: {rationale}".strip()
                )
                logger.warning("primary_agent_governance_deny tool=%s rationale=%s", name, rationale)
                return msg
            if decision_str == "needs_approval":
                msg = (
                    f"Governance NEEDS_APPROVAL for tool {name!r}: "
                    f"{rationale}".strip()
                )
                logger.info(
                    "primary_agent_governance_needs_approval tool=%s rationale=%s",
                    name,
                    rationale,
                )
                return msg
        except Exception as exc:  # noqa: BLE001 — never let governance brick the chain
            logger.warning(
                "primary_agent_governance_check_failed tool=%s err=%s",
                name,
                exc,
            )
            return None
        return None

    async def execute(
        self,
        name: str,
        arguments: str,
        context: AgentContext | None = None,
    ) -> str:
        """Route the tool call to the appropriate handler.

        For specialist tools (``search`` / ``pentest`` / ``code`` / ``advice``
        / ``memorize`` / ``maintain``) a governance pre-check is performed;
        a ``DENY`` (or ``NEEDS_APPROVAL``) decision short-circuits the call
        and returns a human-readable error string to the LLM without invoking
        the specialist handler. Barrier tools (``done`` / ``ask``) bypass the
        gate.
        """
        # Governance pre-check (specialists only).
        denial = self._check_governance(name, arguments, context)
        if denial is not None:
            return denial

        if name in SPECIALIST_TOOL_NAMES:
            handler: SpecialistHandler = self._handlers[name]
            result = handler(arguments, context)
        elif name in BARRIER_TOOL_NAMES:
            barrier_handler: BarrierHandler = self._handlers["barrier"]
            result = barrier_handler(name, arguments, context)
        else:
            raise ValueError(f"PrimaryAgent: no handler registered for tool {name!r}")

        if asyncio.iscoroutine(result):
            result = await result
        return result  # type: ignore[return-value]

    def is_barrier(self, name: str) -> bool:
        """Return True for ``done`` / ``ask``."""
        return name in BARRIER_TOOL_NAMES

    def get_tools(self) -> list[dict[str, Any]]:
        """Return a shallow-copied list of the tool schemas."""
        return [dict(schema) for schema in self._schemas]


# ---------------------------------------------------------------------------
# Per-run bookkeeping.
# ---------------------------------------------------------------------------


@dataclass
class PrimaryAgentRunStats:
    """Bookkeeping for a single ``PrimaryAgent.run()`` invocation.

    Populated by ``PrimaryAgent.run()`` after the chain terminates; accessible
    via ``PrimaryAgent.stats``. Useful for telemetry, debugging, and
    asserting on test behaviour.
    """

    iterations: int = 0
    tool_calls_made: list[ToolCall] = field(default_factory=list)
    barrier_hit: str | None = None
    final_result: PerformResult = PerformResult.ERROR
    started_at: str = ""
    finished_at: str = ""


# ---------------------------------------------------------------------------
# PrimaryAgent — the root orchestrator.
# ---------------------------------------------------------------------------


class PrimaryAgent:
    """Root orchestrator ported from the Go original's ``flowProvider.PerformAgentChain``.

    The PrimaryAgent renders its system prompt, seeds the message chain with
    ``[system, user(subtask_description)]``, then drives
    :func:`perform_agent_chain` with the 6 specialist tools + 2 barrier
    tools. When the LLM invokes ``done``, the chain terminates with
    ``PerformResult.DONE`` (or ``PerformResult.ERROR`` if ``success=False``);
    when it invokes ``ask``, with ``PerformResult.WAITING``.

    The 6 specialists and the barrier handler are injected via
    ``tool_handlers`` so this class stays decoupled from the concrete
    specialist implementations (built by parallel subagents).

    Example:
        >>> llm = MyLLMClient()
        >>> handlers = {
        ...     "search":   searcher.run,
        ...     "pentest":  pentester.run,
        ...     "code":     coder.run,
        ...     "advice":   adviser.run,
        ...     "memorize": memorist.run,
        ...     "maintain": installer.run,
        ...     "barrier":  barrier_handler,
        ... }
        >>> agent = PrimaryAgent(llm, handlers)
        >>> result = await agent.run("Enumerate subdomains of example.com")

    Note:
        ``PrimaryAgent`` instances are NOT concurrency-safe: ``run()``
        mutates ``self._chain`` and ``self._stats``. Callers must either use
        one instance per concurrent subtask or serialise ``run()`` calls with
        an ``asyncio.Lock``.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_handlers: dict[str, Any],
        *,
        max_iterations: int = MAX_GENERAL_ITERATIONS,
        governance: Any | None = None,
        memory: Any | None = None,
        reflector: Any | None = None,
        summarizer: Any | None = None,
        lang: str = "English",
        execution_context: str = "",
        system_prompt: str | None = None,
        tool_schemas: list[dict[str, Any]] | None = None,
        docker_image: str = "debian:latest",
        cwd: str = "/work",
        use_sandbox: bool = False,
        sandbox: Any | None = None,
        safe_exec_fn: Any | None = None,
        search_registry: Any | None = None,
    ) -> None:
        """Initialise the PrimaryAgent.

        Args:
            llm_client: LLM client implementing the :class:`LLMClient`
                protocol.
            tool_handlers: Dict mapping tool names to handlers. Must include
                the 6 specialist keys (``search``, ``pentest``, ``code``,
                ``advice``, ``memorize``, ``maintain``) and a ``barrier``
                key. Specialist handlers are ``(args_json, ctx) -> str``;
                the barrier handler is ``(tool_name, args_json, ctx) -> str``.
            max_iterations: Iteration cap for the chain (default 100, the
                SecurAgentX general-agent cap).
            governance: Optional governance gate (e.g. an
                ``securagentx.governance.GovernanceGate`` instance). When
                supplied, every specialist tool call is policy-checked before
                dispatch; a ``DENY`` decision short-circuits the call and
                returns a human-readable error string to the LLM. Barrier
                tools (``done`` / ``ask``) bypass the gate.
            memory: Optional memory manager. If a ``securagentx.agent.memory.
                AgentMemory`` instance is supplied it is forwarded to the
                executor and exposed via :meth:`get_infra` so specialist
                handlers can recall/store context. If ``None``, an
                ``AgentMemory`` is constructed lazily on first use via
                :meth:`_get_agent_memory` (best-effort; silently returns
                ``None`` when ChromaDB is unavailable).
            reflector: Optional :class:`Reflector` for no-tool-call repair.
                If ``None``, any no-tool-call response terminates the chain
                with ``PerformResult.ERROR``.
            summarizer: Optional :class:`Summarizer` for context-window
                management.
            lang: Engagement-log language.
            execution_context: Pre-rendered XML execution-context string.
            system_prompt: Optional fully-rendered system prompt; if
                ``None``, rendered lazily on first ``run()`` via
                :func:`render_system_prompt`.
            tool_schemas: Optional override for the JSON-schema tool list.
            docker_image: Docker image name injected into the prompt.
            cwd: Working-directory path injected into the prompt.
            use_sandbox: When ``True``, lazily construct a
                ``securagentx.docker.sandbox.DockerSandbox`` on first
                ``run()`` and forward it to the executor (specialists can
                then run commands inside the container via the wired
                infrastructure). Defaults to ``False`` (host execution via
                ``safe_exec``).
            sandbox: Optional pre-built ``DockerSandbox`` instance. When
                ``None`` and ``use_sandbox`` is ``True``, one is constructed
                lazily. When ``None`` and ``use_sandbox`` is ``False``, no
                sandbox is wired.
            safe_exec_fn: Optional callable matching
                ``tools.safe_exec.execute_safely``. When ``None``, the real
                ``execute_safely`` is imported lazily on first use via
                :meth:`_get_safe_exec`.
            search_registry: Optional
                ``securagentx.search_providers.registry.SearchProviderRegistry``
                instance. When ``None``, the default singleton is fetched
                lazily via :meth:`_get_search_registry` (best-effort; silently
                returns ``None`` when no providers are configured).
        """
        self._llm_client = llm_client
        self._tool_handlers = tool_handlers
        self._max_iterations = max_iterations
        self._governance = governance
        self._memory = memory
        self._reflector = reflector
        self._summarizer = summarizer
        self._lang = lang
        self._execution_context = execution_context
        self._system_prompt_override = system_prompt
        self._tool_schemas = tool_schemas
        self._docker_image = docker_image
        self._cwd = cwd
        self._use_sandbox = bool(use_sandbox)
        self._sandbox_override = sandbox
        self._safe_exec_fn_override = safe_exec_fn
        self._search_registry_override = search_registry
        self._log = logger.getChild("PrimaryAgent")

        # Lazily-initialised VulnAgent infrastructure — all ``None`` until
        # first access via the corresponding ``_get_*`` helper. Keeping them
        # lazy means the module imports cleanly even when Docker / ChromaDB /
        # httpx are not installed (e.g. in unit tests).
        self._sandbox_cache: Any | None = None
        self._sandbox_initialised: bool = False
        self._agent_memory_cache: Any | None = None
        self._agent_memory_initialised: bool = False
        self._safe_exec_cache: Any | None = None
        self._safe_exec_initialised: bool = False
        self._search_registry_cache: Any | None = None
        self._search_registry_initialised: bool = False

        # Per-run state — reset at the start of each run() call.
        self._chain: list[Message] = []
        self._stats: PrimaryAgentRunStats = PrimaryAgentRunStats()

    # ------------------------------------------------------------------
    # VulnAgent infrastructure — lazy initialisers (sandbox / memory /
    # safe_exec / search registry). All silent-fallback so test envs without
    # Docker / ChromaDB / httpx keep working.
    # ------------------------------------------------------------------

    def _get_safe_exec(self) -> Any | None:
        """Return a callable matching ``tools.safe_exec.execute_safely``.

        Resolution order:

        1. Caller-supplied ``safe_exec_fn`` (constructor arg).
        2. Lazy import of ``tools.safe_exec.execute_safely``.
        3. ``None`` (silent fallback — specialists fall back to plain
           ``subprocess``).
        """
        if self._safe_exec_initialised:
            return self._safe_exec_cache
        self._safe_exec_initialised = True
        if self._safe_exec_fn_override is not None:
            self._safe_exec_cache = self._safe_exec_fn_override
            return self._safe_exec_cache
        try:
            from tools.safe_exec import execute_safely  # type: ignore[import]
            self._safe_exec_cache = execute_safely
        except Exception as exc:  # noqa: BLE001
            self._log.debug("safe_exec_unavailable err=%s", exc)
            self._safe_exec_cache = None
        return self._safe_exec_cache

    def _get_agent_memory(self) -> Any | None:
        """Return an ``AgentMemory`` instance (cached, lazy).

        Resolution order:

        1. Caller-supplied ``memory`` (constructor arg) if it looks like an
           ``AgentMemory`` (duck-typed by ``pre_hunt`` attribute).
        2. Lazy construction of ``securagentx.agent.memory.AgentMemory``.
        3. ``None`` (silent fallback — ChromaDB unavailable).
        """
        if self._agent_memory_initialised:
            return self._agent_memory_cache
        self._agent_memory_initialised = True
        if self._memory is not None and hasattr(self._memory, "pre_hunt"):
            self._agent_memory_cache = self._memory
            return self._agent_memory_cache
        try:
            from securagentx.agent.memory import AgentMemory  # type: ignore[import]
            self._agent_memory_cache = AgentMemory()
        except Exception as exc:  # noqa: BLE001
            self._log.debug("agent_memory_unavailable err=%s", exc)
            self._agent_memory_cache = None
        return self._agent_memory_cache

    def _get_search_registry(self) -> Any | None:
        """Return a ``SearchProviderRegistry`` instance (cached, lazy).

        Resolution order:

        1. Caller-supplied ``search_registry`` (constructor arg).
        2. ``securagentx.search_providers.registry.get_default_registry()``
           (process-wide singleton).
        3. ``None`` (silent fallback — no providers configured).
        """
        if self._search_registry_initialised:
            return self._search_registry_cache
        self._search_registry_initialised = True
        if self._search_registry_override is not None:
            self._search_registry_cache = self._search_registry_override
            return self._search_registry_cache
        try:
            from securagentx.search_providers.registry import (  # type: ignore[import]
                get_default_registry,
            )
            self._search_registry_cache = get_default_registry()
        except Exception as exc:  # noqa: BLE001
            self._log.debug("search_registry_unavailable err=%s", exc)
            self._search_registry_cache = None
        return self._search_registry_cache

    def _get_sandbox(self) -> Any | None:
        """Return a ``DockerSandbox`` instance (cached, lazy).

        Resolution order:

        1. Caller-supplied ``sandbox`` (constructor arg).
        2. Lazy construction of ``securagentx.docker.sandbox.DockerSandbox``
           — only when ``use_sandbox=True``.
        3. ``None`` (silent fallback — specialists use ``safe_exec`` on the
           host instead).
        """
        if self._sandbox_initialised:
            return self._sandbox_cache
        self._sandbox_initialised = True
        if self._sandbox_override is not None:
            self._sandbox_cache = self._sandbox_override
            return self._sandbox_cache
        if not self._use_sandbox:
            self._sandbox_cache = None
            return self._sandbox_cache
        try:
            from securagentx.docker.sandbox import DockerSandbox  # type: ignore[import]
            self._sandbox_cache = DockerSandbox(default_image=self._docker_image)
        except Exception as exc:  # noqa: BLE001
            self._log.warning("docker_sandbox_unavailable err=%s -- falling back to host", exc)
            self._sandbox_cache = None
        return self._sandbox_cache

    # ------------------------------------------------------------------
    # Public convenience wrappers — expose the wired VulnAgent tools to
    # specialist handlers / external callers. All silent-fallback.
    # ------------------------------------------------------------------

    def safe_execute_command(
        self,
        command: str,
        timeout: int = 300,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Run ``command`` via ``tools.safe_exec.execute_safely``.

        Returns the structured ``{success, stdout, stderr, exit_code, error}``
        dict. When ``safe_exec`` is unavailable (e.g. in unit tests), returns
        an error-shaped dict with ``success=False`` so callers can branch on
        the ``success`` flag without try/except.
        """
        fn = self._get_safe_exec()
        if fn is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "error": "safe_exec unavailable",
            }
        try:
            return fn(command, timeout=timeout, cwd=cwd)
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "error": f"safe_exec raised: {exc}",
            }

    async def search(self, query: str, max_results: int = 5) -> dict[str, str]:
        """Fan ``query`` out to every available search provider.

        Returns the ``{provider_name: result_string}`` dict from
        ``SearchProviderRegistry.search_all``. Returns ``{}`` when no
        registry is wired / no providers are configured.
        """
        registry = self._get_search_registry()
        if registry is None:
            return {}
        try:
            return await registry.search_all(query, max_results=max_results)
        except Exception as exc:  # noqa: BLE001
            self._log.warning("search_failed query=%r err=%s", query[:80], exc)
            return {}

    def recall_memory(self, target: str) -> dict[str, Any]:
        """Recall past memories / learned skills for ``target``.

        Thin wrapper around ``AgentMemory.pre_hunt``. Returns the
        ``{memories, learned_skills, context}`` dict, or an empty-shaped dict
        when no memory engine is wired.
        """
        memory = self._get_agent_memory()
        if memory is None:
            return {"memories": [], "learned_skills": [], "context": ""}
        try:
            return memory.pre_hunt(target)
        except Exception as exc:  # noqa: BLE001
            self._log.warning("memory_recall_failed target=%r err=%s", target, exc)
            return {"memories": [], "learned_skills": [], "context": ""}

    def get_sandbox(self) -> Any | None:
        """Return the wired ``DockerSandbox`` (or ``None`` if not configured)."""
        return self._get_sandbox()

    def get_governance(self) -> Any | None:
        """Return the wired ``GovernanceGate`` (or ``None`` if not configured)."""
        return self._governance

    # ------------------------------------------------------------------
    # Read-only views for callers / tests.
    # ------------------------------------------------------------------

    @property
    def chain(self) -> list[Message]:
        """Return a shallow copy of the current message chain."""
        return list(self._chain)

    @property
    def stats(self) -> PrimaryAgentRunStats:
        """Return the stats from the most recent ``run()``."""
        return self._stats

    @property
    def agent_type(self) -> AgentType:
        """Return the agent type (always ``AgentType.PRIMARY``)."""
        return AgentType.PRIMARY

    # ------------------------------------------------------------------
    # System-prompt rendering.
    # ------------------------------------------------------------------

    def _render_system_prompt(self) -> str:
        """Render (or return the override for) the system prompt."""
        if self._system_prompt_override is not None:
            return self._system_prompt_override
        return render_system_prompt(
            lang=self._lang,
            cwd=self._cwd,
            docker_image=self._docker_image,
            execution_context=self._execution_context,
        )

    # ------------------------------------------------------------------
    # Barrier callback — translates barrier hits into PerformResult.
    # ------------------------------------------------------------------

    def _make_barrier_callback(self) -> Callable[[str, str], PerformResult]:
        """Build the ``on_barrier`` callback used by ``perform_agent_chain``.

        - ``done`` with ``success=True``  -> ``PerformResult.DONE``
        - ``done`` with ``success=False`` -> ``PerformResult.ERROR``
        - ``ask``                         -> ``PerformResult.WAITING``
        - unknown barrier                 -> ``PerformResult.DONE`` (default)
        """

        def _on_barrier(name: str, args_json: str) -> PerformResult:
            self._stats.barrier_hit = name
            if name == DONE_TOOL_NAME:
                # Parse the ``success`` flag (default True on parse failure
                # to mirror the original optimistic default).
                try:
                    payload = json.loads(args_json) if args_json else {}
                except json.JSONDecodeError:
                    payload = {}
                if payload.get("success", True):
                    return PerformResult.DONE
                return PerformResult.ERROR
            if name == ASK_TOOL_NAME:
                return PerformResult.WAITING
            self._log.warning("unknown_barrier_tool name=%s -- defaulting to DONE", name)
            return PerformResult.DONE

        return _on_barrier

    # ------------------------------------------------------------------
    # Main entry point.
    # ------------------------------------------------------------------

    async def run(self, subtask_description: str) -> PerformResult:
        """Execute ``subtask_description`` via ``perform_agent_chain``.

        Renders the system prompt, seeds the chain with
        ``[system, user(subtask_description)]``, then drives the universal
        agent-chain loop with the 6 specialist tools + 2 barrier tools.

        Args:
            subtask_description: The subtask to execute (typically rendered
                from the Generator's subtask plan).

        Returns:
            * ``PerformResult.DONE`` if the LLM closed via ``done`` with
              ``success=True``.
            * ``PerformResult.WAITING`` if the LLM paused via ``ask``.
            * ``PerformResult.ERROR`` on iteration-limit exhaustion,
              unrecoverable errors, or ``done`` with ``success=False``.
        """
        # Reset per-run state.
        self._chain = []
        self._stats = PrimaryAgentRunStats(
            started_at=datetime.now(timezone.utc).isoformat(),
            final_result=PerformResult.ERROR,
        )

        # Render system prompt and seed the chain.
        system_prompt = self._render_system_prompt()
        self._chain.append(Message(role="system", content=system_prompt))
        self._chain.append(Message(role="user", content=subtask_description))

        # Build the executor and barrier callback.
        # Wire VulnAgent infrastructure (governance / memory / sandbox /
        # safe_exec / search registry) into the executor so specialist
        # handlers can reach them via ``executor.get_infra()``. All are
        # lazy / silent-fallback — specialists degrade to host execution
        # when Docker / ChromaDB / httpx are unavailable.
        executor = _PrimaryToolExecutor(
            tool_handlers=self._tool_handlers,
            tool_schemas=self._tool_schemas,
            governance=self._governance,
            memory=self._get_agent_memory(),
            docker_sandbox=self._get_sandbox(),
            safe_exec_fn=self._get_safe_exec(),
            search_registry=self._get_search_registry(),
        )
        barrier_callback = self._make_barrier_callback()

        self._log.info("primary_agent_run_start subtask=%r", subtask_description[:200])

        try:
            result = await perform_agent_chain(
                agent_type=AgentType.PRIMARY,
                chain=self._chain,
                llm_client=self._llm_client,
                executor=executor,
                reflector=self._reflector,
                summarizer=self._summarizer,
                max_iterations=self._max_iterations,
                execution_context=self._execution_context,
                on_barrier=barrier_callback,
            )
        except asyncio.CancelledError:
            self._log.warning("primary_agent_run_cancelled")
            self._stats.finished_at = datetime.now(timezone.utc).isoformat()
            self._stats.final_result = PerformResult.ERROR
            raise
        except Exception as exc:  # noqa: BLE001
            self._log.error("primary_agent_run_failed err=%s", exc)
            self._stats.finished_at = datetime.now(timezone.utc).isoformat()
            self._stats.final_result = PerformResult.ERROR
            return PerformResult.ERROR

        # Tally stats from the (mutated) chain.
        self._stats.iterations = sum(1 for m in self._chain if m.role == "assistant")
        self._stats.tool_calls_made = [
            tc for m in self._chain if m.role == "assistant" for tc in m.tool_calls
        ]
        self._stats.final_result = result
        self._stats.finished_at = datetime.now(timezone.utc).isoformat()

        self._log.info(
            "primary_agent_run_done result=%s iterations=%d tool_calls=%d " "barrier=%s",
            result.value,
            self._stats.iterations,
            len(self._stats.tool_calls_made),
            self._stats.barrier_hit,
        )
        return result


# ---------------------------------------------------------------------------
# Minimal duck-typed stand-in for ``securagentx.types.AIAction`` — used by
# ``_PrimaryToolExecutor._check_governance`` when ``securagentx.types`` is
# not importable (e.g. isolated unit tests). Only the attributes the
# governance gate reads are populated.
# ---------------------------------------------------------------------------


@dataclass
class _MinimalAction:
    """Duck-typed AIAction stand-in for governance checks.

    The ``GovernanceGate.gate`` method reads ``action.action_type`` (via
    ``.value`` if it has one, else ``str()``), ``action.tool``,
    ``action.risk_level``, and ``action.parameters``. This dataclass
    populates those fields with the right shape so governance works without
    a hard dependency on ``securagentx.types``.
    """

    action_type: str = "recon"
    tool: str = ""
    target: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "safe"
    description: str = ""


__all__ = [
    "PrimaryAgent",
    "PrimaryAgentRunStats",
    "render_system_prompt",
    "PRIMARY_AGENT_SYSTEM_PROMPT_TEMPLATE",
    "DONE_TOOL_NAME",
    "ASK_TOOL_NAME",
    "SEARCH_TOOL_NAME",
    "PENTESTER_TOOL_NAME",
    "CODER_TOOL_NAME",
    "ADVICE_TOOL_NAME",
    "MEMORIST_TOOL_NAME",
    "MAINTENANCE_TOOL_NAME",
    "SPECIALIST_TOOL_NAMES",
    "BARRIER_TOOL_NAMES",
    "SpecialistHandler",
    "BarrierHandler",
]
