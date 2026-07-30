"""securagentx/flows/concrete_provider.py — ConcreteFlowProvider implementation.

Wires the :class:`securagentx.flows.flow_worker.FlowProvider` Protocol to the
concrete agent layer defined in :mod:`securagentx.agents`. Each Protocol
method lazily imports its agent module (to avoid circular imports — the
agents package is heavy and not all callers need it), builds the agent with
the provider's configured LLM client / memory / governance / search
providers, and delegates the call.

Delegation map (mirrors the original ``flowProvider`` interface):

* :meth:`get_task_title`           — single tiny LLM call (or fallback).
* :meth:`generate_subtasks`        — :class:`securagentx.agents.generator.Generator`.
* :meth:`refine_subtasks`          — :class:`securagentx.agents.refiner.Refiner`.
* :meth:`prepare_agent_chain`      — inserts a ``PRIMARY_AGENT`` msgchain row.
* :meth:`perform_agent_chain`      — :class:`securagentx.agents.primary_agent.PrimaryAgent`
  (which drives :func:`securagentx.agents.base.perform_agent_chain`).
* :meth:`ensure_chain_consistency` — basic no-op (chain IDs are fresh UUIDs).
* :meth:`put_input_to_agent_chain` — appends a ``user`` message to the chain JSON.
* :meth:`get_task_result`          — :class:`securagentx.agents.reporter.Reporter`.

The provider is constructed once per flow (by the
``_default_provider_factory`` in :mod:`securagentx.flows.manager`) with the
flow's :class:`FlowContext`, then handed to the :class:`FlowWorker` for the
lifetime of the flow.
"""

from __future__ import annotations

import logging
from typing import Any

from securagentx.flows.flow_worker import FlowContext, TaskResult

logger = logging.getLogger("securagentx.flows.concrete_provider")


class ConcreteFlowProvider:
    """Concrete :class:`FlowProvider` that delegates to the agent layer.

    Implements the :class:`securagentx.flows.flow_worker.FlowProvider`
    Protocol. Each method lazily imports its agent module (to avoid
    circular imports), builds the agent, and delegates the call. All
    methods log + re-raise on error so callers can implement their own
    retry / status-transition policy.

    Args:
        ctx: The per-flow :class:`FlowContext` (carries the DB handle,
            flow / user IDs, trace ID). Required — supplied by the
            ``_default_provider_factory`` in :mod:`securagentx.flows.manager`.
        llm_client: Optional LLM client implementing the
            :class:`securagentx.agents.base.LLMClient` Protocol. When
            ``None``, the planning / reporting agents will fail at runtime
            (they require an LLM); :meth:`get_task_title` falls back to a
            deterministic truncation.
        memory: Optional memory manager (e.g. a ``CognitiveMemoryManager``)
            passed through to the PrimaryAgent for specialist retrieval.
        governance: Optional governance gate (e.g. a
            :class:`securagentx.governance.GovernanceGate` instance)
            consulted by the PrimaryAgent before risky tool calls.
        search_providers: Optional list of search-provider instances
            (e.g. Tavily, SearXNG) used by the Searcher specialist. Stored
            for downstream specialist wiring.
    """

    def __init__(
        self,
        ctx: FlowContext,
        *,
        llm_client: Any | None = None,
        memory: Any | None = None,
        governance: Any | None = None,
        search_providers: Any | None = None,
    ) -> None:
        self._ctx: FlowContext = ctx
        self._llm_client = llm_client
        self._memory = memory
        self._governance = governance
        self._search_providers = search_providers

    # ------------------------------------------------------------------
    # Convenience accessors.
    # ------------------------------------------------------------------

    @property
    def ctx(self) -> FlowContext:
        """The per-flow :class:`FlowContext`."""
        return self._ctx

    @property
    def db(self) -> Any:
        """The :class:`FlowDB` from the flow context."""
        return self._ctx.db

    @property
    def flow_id(self) -> int:
        return self._ctx.flow_id

    @property
    def user_id(self) -> int:
        return self._ctx.user_id

    # ------------------------------------------------------------------
    # FlowProvider protocol methods.
    # ------------------------------------------------------------------

    async def get_task_title(self, input: str) -> str:
        """Derive a short task title from ``input`` via a tiny LLM call.

        Falls back to a deterministic truncation when no LLM client is
        configured or the call fails — the title is non-critical (it is
        only used as a display label and may be overridden later).
        """
        text = (input or "").strip().replace("\n", " ")
        try:
            if not text:
                return "Untitled task"
            if self._llm_client is None:
                logger.debug(
                    "get_task_title no_llm -- using truncation fallback "
                    "input_len=%d",
                    len(text),
                )
                return self._truncate_title(text)

            # Lazy import to avoid circular dependency.
            from securagentx.agents.base import AgentType, Message

            prompt = (
                "Summarize the following user request as a concise task "
                "title (<= 80 characters, no quotes, no trailing period, "
                "no leading whitespace):\n\n" + text
            )
            chain = [
                Message(role="system", content="You are a task-title summarizer."),
                Message(role="user", content=prompt),
            ]
            resp = await self._llm_client.call(
                chain, tools=None, agent_type=AgentType.ASSISTANT
            )
            title = (
                (resp.content or "").strip().replace("\n", " ").strip('"').strip("'")
            )
            if not title:
                title = self._truncate_title(text)
            if len(title) > 200:
                title = title[:200].rstrip() + "..."
            logger.debug(
                "get_task_title llm_title=%r input_len=%d", title, len(text)
            )
            return title
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "get_task_title failed err=%s -- using truncation fallback",
                exc,
            )
            return self._truncate_title(text) or "Untitled task"

    async def generate_subtasks(self, task_id: int) -> list:
        """Decompose the task into an ordered subtask plan via the Generator.

        Returns:
            A list of :class:`securagentx.flows.models.SubtaskInfo` objects
            (each with ``title`` and ``description``) in execution order.

        Raises:
            RuntimeError: If the task is not found in the DB.
            Exception: Re-raises any error from the Generator agent.
        """
        try:
            # Lazy imports to avoid circular dependencies.
            from securagentx.agents.base import AgentContext, AgentType
            from securagentx.agents.generator import Generator
            from securagentx.flows.models import SubtaskInfo

            task = await self.db.get_task(task_id)
            if task is None:
                raise RuntimeError(f"task {task_id} not found")

            # Gather prior tasks (for learning context) and prior subtasks
            # (as examples only) — mirrors the original Generator prompt.
            all_tasks = await self.db.list_tasks(self.flow_id)
            previous_tasks = [self._task_to_dict(t) for t in all_tasks if t.id != task_id]
            previous_subtasks: list[dict[str, Any]] = []
            for t in all_tasks:
                if t.id == task_id:
                    continue
                sts = await self.db.list_subtasks(t.id)
                for st in sts:
                    previous_subtasks.append(
                        {
                            "task_id": t.id,
                            "id": st.id,
                            "title": st.title,
                            "description": st.description,
                            "status": self._status_value(st.status),
                            "result": st.result or "",
                        }
                    )

            task_dict = {
                "id": task.id,
                "input": task.input,
                "title": task.title,
            }

            agent = Generator()
            token = AgentContext.put(AgentType.PRIMARY)
            try:
                ctx = AgentContext.current() or AgentContext()
                plan_dicts = await agent.run(
                    ctx=ctx,
                    task=task_dict,
                    previous_tasks=previous_tasks,
                    previous_subtasks=previous_subtasks,
                )
            finally:
                AgentContext.reset(token)

            subtasks = [SubtaskInfo.model_validate(d) for d in plan_dicts]
            logger.info(
                "generate_subtasks task_id=%d count=%d", task_id, len(subtasks)
            )
            return subtasks
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "generate_subtasks failed task_id=%d err=%s", task_id, exc
            )
            raise

    async def refine_subtasks(self, task_id: int) -> list:
        """Produce a delta-patched subtask plan via the Refiner.

        Returns:
            A list of :class:`securagentx.flows.models.SubtaskInfo` objects
            representing the *new* full plan (the caller deletes the old
            ``CREATED`` subtasks and inserts the new ones).

        Raises:
            RuntimeError: If the task is not found in the DB.
            Exception: Re-raises any error from the Refiner agent.
        """
        try:
            # Lazy imports.
            from securagentx.agents.base import AgentContext, AgentType
            from securagentx.agents.refiner import Refiner
            from securagentx.flows.models import SubtaskInfo, SubtaskStatus

            task = await self.db.get_task(task_id)
            if task is None:
                raise RuntimeError(f"task {task_id} not found")

            # Partition existing subtasks into completed / planned.
            all_subtasks = await self.db.list_subtasks(task_id)
            completed: list[dict[str, Any]] = []
            planned: list[dict[str, Any]] = []
            for st in all_subtasks:
                status_val = self._status_value(st.status)
                entry = {
                    "id": st.id,
                    "title": st.title,
                    "description": st.description,
                    "status": status_val,
                    "result": st.result or "",
                }
                if status_val == SubtaskStatus.CREATED.value:
                    # Refiner's prompt expects planned subtasks without
                    # status / result (they are still pending).
                    planned.append(
                        {k: entry[k] for k in ("id", "title", "description")}
                    )
                else:
                    completed.append(entry)

            # Prior tasks (learning context only).
            all_tasks = await self.db.list_tasks(self.flow_id)
            previous_tasks = [
                self._task_to_dict(t) for t in all_tasks if t.id != task_id
            ]

            task_dict = {
                "id": task.id,
                "input": task.input,
                "title": task.title,
            }

            agent = Refiner()
            token = AgentContext.put(AgentType.PRIMARY)
            try:
                ctx = AgentContext.current() or AgentContext()
                plan_dicts = await agent.run(
                    ctx=ctx,
                    task=task_dict,
                    completed_subtasks=completed,
                    planned_subtasks=planned,
                    previous_tasks=previous_tasks,
                )
            finally:
                AgentContext.reset(token)

            subtasks = [SubtaskInfo.model_validate(d) for d in plan_dicts]
            logger.info(
                "refine_subtasks task_id=%d new_count=%d",
                task_id,
                len(subtasks),
            )
            return subtasks
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "refine_subtasks failed task_id=%d err=%s", task_id, exc
            )
            raise

    async def prepare_agent_chain(
        self, task_id: int, subtask_id: int
    ) -> int:
        """Insert a fresh primary-agent msgchain row and return its ID.

        Mirrors the original ``flowProvider.PrepareAgentChain`` — allocates
        a new ``PRIMARY_AGENT`` msgchain for the subtask so the subsequent
        :meth:`perform_agent_chain` call has a chain to drive.
        """
        try:
            # Lazy import.
            from securagentx.flows.models import MsgchainType

            mc = await self.db.create_msgchain(
                type=MsgchainType.PRIMARY_AGENT,
                flow_id=self.flow_id,
                task_id=task_id,
                subtask_id=subtask_id,
                chain=[],
            )
            logger.info(
                "prepare_agent_chain task_id=%d subtask_id=%d msg_chain_id=%d",
                task_id,
                subtask_id,
                mc.id,
            )
            return int(mc.id)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "prepare_agent_chain failed task_id=%d subtask_id=%d err=%s",
                task_id,
                subtask_id,
                exc,
            )
            raise

    async def perform_agent_chain(
        self, task_id: int, subtask_id: int, msg_chain_id: int
    ) -> Any:
        """Drive the PrimaryAgent chain for one subtask.

        Builds a :class:`PrimaryAgent` with the provider's LLM client /
        memory / governance and calls ``agent.run(subtask_description)``,
        which in turn drives
        :func:`securagentx.agents.base.perform_agent_chain`. The resulting
        chain is persisted back to the msgchain row so a resumed subtask
        can inspect the prior turn.

        Returns:
            The :class:`securagentx.agents.base.PerformResult` (``DONE``,
            ``WAITING``, or ``ERROR``) from the chain. On unexpected
            errors, returns ``PerformResult.ERROR`` (rather than
            re-raising) so the :class:`SubtaskWorker` can transition the
            subtask to ``FAILED`` cleanly.
        """
        try:
            # Lazy imports.
            from securagentx.agents.base import (
                AgentContext,
                AgentType,
            )
            from securagentx.agents.primary_agent import PrimaryAgent

            subtask = await self.db.get_subtask(subtask_id)
            if subtask is None:
                raise RuntimeError(f"subtask {subtask_id} not found")

            description = subtask.description or subtask.title or ""

            # Specialist handlers are not wired here — they are a downstream
            # concern (the specialists are built by separate subagents).
            # An empty handlers dict means the PrimaryAgent will terminate
            # via the iteration cap if the LLM never invokes a barrier tool;
            # this keeps the provider functional for unit tests while
            # leaving the specialist wiring to the application bootstrap.
            tool_handlers: dict[str, Any] = {}
            agent = PrimaryAgent(
                llm_client=self._llm_client,  # type: ignore[arg-type]
                tool_handlers=tool_handlers,
                governance=self._governance,
                memory=self._memory,
            )

            token = AgentContext.put(AgentType.PRIMARY)
            try:
                result = await agent.run(description)
            finally:
                AgentContext.reset(token)

            # Persist the resulting chain back to the DB (for resume / audit).
            try:
                chain_dicts = [self._message_to_dict(m) for m in agent.chain]
                await self.db.update_msgchain(msg_chain_id, chain=chain_dicts)
            except Exception as persist_exc:  # noqa: BLE001
                logger.warning(
                    "perform_agent_chain persist_failed msg_chain_id=%d err=%s",
                    msg_chain_id,
                    persist_exc,
                )

            logger.info(
                "perform_agent_chain task_id=%d subtask_id=%d msg_chain_id=%d "
                "result=%s",
                task_id,
                subtask_id,
                msg_chain_id,
                result.value if hasattr(result, "value") else str(result),
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "perform_agent_chain failed task_id=%d subtask_id=%d "
                "msg_chain_id=%d err=%s",
                task_id,
                subtask_id,
                msg_chain_id,
                exc,
            )
            # Return ERROR rather than re-raising so the SubtaskWorker can
            # transition the subtask to FAILED cleanly (mirrors the
            # original Go behavior where PerformAgentChain never panics).
            from securagentx.agents.base import PerformResult as _PerformResult

            return _PerformResult.ERROR

    async def ensure_chain_consistency(self, msg_chain_id: int) -> None:
        """Rewrite stale chain IDs / fix tool-call ID collisions on resume.

        Basic implementation: **no-op**. The chain persisted by
        :meth:`perform_agent_chain` already uses fresh UUIDs for every
        tool call, so there are no stale IDs to rewrite on the next run.
        Downstream providers may override this to perform real rewriting
        (e.g. deduplicating tool-call IDs that the LLM has forgotten).
        """
        logger.debug(
            "ensure_chain_consistency msg_chain_id=%d (no-op)", msg_chain_id
        )
        return None

    async def put_input_to_agent_chain(
        self, msg_chain_id: int, input: str
    ) -> None:
        """Append user ``input`` to a WAITING agent chain (for resume).

        Loads the msgchain's persisted chain JSON, appends a fresh
        ``{"role": "user", "content": input}`` entry, and writes it back.
        Called by :meth:`SubtaskWorker.put_input` when the user supplies
        new input to a paused subtask.
        """
        try:
            mc = await self.db.get_msgchain(msg_chain_id)
            if mc is None:
                raise RuntimeError(f"msgchain {msg_chain_id} not found")
            chain = list(mc.chain or [])
            chain.append({"role": "user", "content": input})
            await self.db.update_msgchain(msg_chain_id, chain=chain)
            logger.info(
                "put_input_to_agent_chain msg_chain_id=%d input_len=%d",
                msg_chain_id,
                len(input),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "put_input_to_agent_chain failed msg_chain_id=%d err=%s",
                msg_chain_id,
                exc,
            )
            raise

    async def get_task_result(self, task_id: int) -> TaskResult:
        """Produce the final task report via the Reporter agent.

        Returns:
            A :class:`TaskResult` dataclass with ``success``, ``result``,
            and ``message`` fields, ready for the :class:`TaskWorker` to
            persist + use for the FINISHED / FAILED transition.

        Raises:
            RuntimeError: If the task is not found in the DB.
            Exception: Re-raises any error from the Reporter agent.
        """
        try:
            # Lazy imports.
            from securagentx.agents.base import AgentContext, AgentType
            from securagentx.agents.reporter import Reporter
            from securagentx.flows.models import SubtaskStatus

            task = await self.db.get_task(task_id)
            if task is None:
                raise RuntimeError(f"task {task_id} not found")

            # Partition subtasks into completed / planned (same as Refiner).
            all_subtasks = await self.db.list_subtasks(task_id)
            completed: list[dict[str, Any]] = []
            planned: list[dict[str, Any]] = []
            for st in all_subtasks:
                status_val = self._status_value(st.status)
                entry = {
                    "id": st.id,
                    "title": st.title,
                    "description": st.description,
                    "status": status_val,
                    "result": st.result or "",
                }
                if status_val == SubtaskStatus.CREATED.value:
                    planned.append(
                        {k: entry[k] for k in ("id", "title", "description")}
                    )
                else:
                    completed.append(entry)

            # Prior tasks (learning context only).
            all_tasks = await self.db.list_tasks(self.flow_id)
            previous_tasks = [
                self._task_to_dict(t) for t in all_tasks if t.id != task_id
            ]

            task_dict = {
                "id": task.id,
                "input": task.input,
                "title": task.title,
            }

            agent = Reporter()
            token = AgentContext.put(AgentType.PRIMARY)
            try:
                ctx = AgentContext.current() or AgentContext()
                result_dict = await agent.run(
                    ctx=ctx,
                    task=task_dict,
                    previous_tasks=previous_tasks,
                    completed_subtasks=completed,
                    planned_subtasks=planned,
                )
            finally:
                AgentContext.reset(token)

            tr = TaskResult(
                success=bool(result_dict.get("success", False)),
                result=str(result_dict.get("result", "")),
                message=str(result_dict.get("message", "")),
            )
            logger.info(
                "get_task_result task_id=%d success=%s result_len=%d",
                task_id,
                tr.success,
                len(tr.result),
            )
            return tr
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "get_task_result failed task_id=%d err=%s", task_id, exc
            )
            raise

    # ------------------------------------------------------------------
    # Internal helpers.
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate_title(text: str, limit: int = 80) -> str:
        """Deterministic title fallback: first ``limit`` chars + ellipsis."""
        text = text.strip()
        if not text:
            return ""
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

    @staticmethod
    def _status_value(status: Any) -> str:
        """Return the string value of an enum / string status."""
        if hasattr(status, "value"):
            return str(status.value)
        return str(status)

    @staticmethod
    def _task_to_dict(t: Any) -> dict[str, Any]:
        """Convert a Task record to the dict shape the agents expect."""
        return {
            "id": t.id,
            "input": t.input,
            "status": ConcreteFlowProvider._status_value(t.status),
            "result": t.result or "",
        }

    @staticmethod
    def _message_to_dict(m: Any) -> dict[str, Any]:
        """Convert a base.Message dataclass to a JSON-serialisable dict.

        Round-trips with the chain JSON persisted in the msgchains table
        (so a resumed subtask can rebuild the chain).
        """
        # Lazy import to avoid circular dependency.
        from securagentx.agents.base import Message

        if isinstance(m, Message):
            return {
                "role": m.role,
                "content": m.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                    for tc in (m.tool_calls or [])
                ],
                "tool_call_id": m.tool_call_id,
                "name": m.name,
                "reasoning": m.reasoning,
                "metadata": dict(m.metadata) if m.metadata else {},
            }
        # Already a dict — pass through unchanged.
        if isinstance(m, dict):
            return m
        # Fallback: coerce unknown shapes to a user-role message.
        return {"role": "user", "content": str(m)}


__all__ = ["ConcreteFlowProvider"]
