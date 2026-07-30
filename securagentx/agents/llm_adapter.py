"""Adapter that wraps :class:`tools.universal_ai_client.UniversalAIClient` so it
satisfies the :class:`securagentx.agents.base.LLMClient` Protocol.

Background
----------
``UniversalAIClient`` is the legacy HTTP client used by single-agent
``VulnAgent``. It exposes:

* ``chat(messages: List[AIMessage], ..., tools=None, tool_choice=None) -> AIResponse``
  (synchronous — built on ``requests.Session``).
* ``chat_async(messages, ...) -> AIResponse`` (async, but does NOT accept
  ``tools`` — so it cannot do native function-calling).
* ``simple_chat(user_message, system_prompt=None) -> str``

The agent-layer :class:`securagentx.agents.base.LLMClient` Protocol requires:

* ``async def call(chain: list[Message], tools: list[dict] | None = None,
  agent_type: AgentType | None = None) -> LLMResponse``

The two type systems are also incompatible:

* ``base.Message`` has 7 fields (role, content, tool_calls, tool_call_id,
  name, reasoning, metadata); ``universal.AIMessage`` has 3 (role, content,
  metadata).
* ``base.ToolCall.arguments`` is a JSON-encoded ``str``;
  ``universal.ToolCall.arguments`` is a parsed ``Dict[str, Any]``.
* ``base.LLMResponse`` has ``content``, ``tool_calls``, ``reasoning``,
  ``info``; ``universal.AIResponse`` has ``content``, ``model``, ``usage``,
  ``raw_response``, ``tool_calls``.

This adapter bridges all four gaps in one small class. It is injected at a
single site (``main.py:_run_multi_agent_flow``) so the single-agent path
(which talks to ``UniversalAIClient`` directly via ``.chat()``) is
untouched — zero regression risk.

Design notes
------------
* We wrap the synchronous ``chat()`` (the only method that accepts
  ``tools=``) in :func:`asyncio.to_thread` so the agent event loop is not
  blocked.
* ``agent_type`` is accepted but ignored — ``UniversalAIClient`` has no
  equivalent concept. We log it at debug level for traceability.
* The adapter exposes ``model`` so call sites like
  ``getattr(client, "model", None)`` in ``main.py`` continue to work.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from securagentx.agents.base import (
    AgentType,
    LLMResponse,
    Message,
    ToolCall,
)

logger = logging.getLogger("securagentx.agents.llm_adapter")


class UniversalAIClientAdapter:
    """Adapts :class:`UniversalAIClient` to the :class:`LLMClient` Protocol.

    Implements ``async def call(chain, tools, agent_type) -> LLMResponse`` by
    delegating to the wrapped client's synchronous ``chat()`` method (the
    only one that supports ``tools=``), offloaded via
    :func:`asyncio.to_thread` so the agent event loop is never blocked.

    Type conversions performed:

    * **Input**: ``list[base.Message]`` → ``list[universal.AIMessage]``
      (only ``role`` + ``content`` are preserved — ``universal.AIMessage``
      does not have ``tool_calls`` / ``tool_call_id`` / ``name`` /
      ``reasoning`` fields).
    * **Tools**: pass-through (both sides use OpenAI function-schema list).
    * **Output**: ``universal.AIResponse`` → ``base.LLMResponse``;

      * ``AIResponse.tool_calls[i].arguments`` (``Dict``) →
        ``base.ToolCall.arguments`` (JSON-encoded ``str`` via
        :func:`json.dumps`).
      * ``AIResponse.model`` + ``AIResponse.usage`` → ``LLMResponse.info``.
      * ``reasoning`` is set to ``None`` (not exposed by ``UniversalAIClient``).
    """

    def __init__(self, inner: Any) -> None:
        """Wrap a :class:`UniversalAIClient` instance.

        Args:
            inner: The :class:`UniversalAIClient` (or any duck-typed object
                exposing ``chat(messages, tools=None, ...) -> AIResponse``
                and a ``model`` attribute).
        """
        self._inner = inner
        # Expose `model` so call sites like `getattr(client, "model", None)`
        # in main.py:_run_multi_agent_flow continue to work after wrapping.
        self.model: str | None = getattr(inner, "model", None)

    async def call(
        self,
        chain: list[Message],
        tools: list[dict[str, Any]] | None = None,
        agent_type: AgentType | None = None,
    ) -> LLMResponse:
        """Call the wrapped ``UniversalAIClient.chat()`` asynchronously.

        Args:
            chain: The agent-chain message list (``base.Message`` objects).
            tools: Optional OpenAI-format tool-schema list (passed through
                unchanged to ``chat()``).
            agent_type: The agent type initiating the call (accepted but
                ignored — ``UniversalAIClient`` has no equivalent concept).

        Returns:
            A :class:`base.LLMResponse` with ``content``, ``tool_calls``
            (each ``ToolCall.arguments`` as a JSON string), and ``info``
            carrying the model name + token usage.
        """
        # Lazy import to avoid a hard cross-package dependency at module
        # load time — keeps `securagentx.agents` importable in test
        # environments where `tools.universal_ai_client` is stubbed.
        from tools.universal_ai_client import AIMessage

        # --- Input conversion: base.Message → universal.AIMessage ---
        # Only role + content survive (universal.AIMessage has no
        # tool_calls / tool_call_id / name / reasoning fields). This is
        # acceptable for the specialist agents because:
        #   1. Specialist chains are short (single system + single user).
        #   2. Tool-call round-tripping (assistant.tool_calls + role="tool"
        #      reply) is not exercised in the current Generator/Refiner/
        #      Reporter/PrimaryAgent flow — they terminate on the first
        #      barrier tool hit.
        ai_messages = [
            AIMessage(role=m.role, content=m.content) for m in chain
        ]

        logger.debug(
            "llm_adapter_call agent_type=%s chain_len=%d tools=%d",
            agent_type.value if agent_type else None,
            len(ai_messages),
            len(tools) if tools else 0,
        )

        # --- Dispatch via the synchronous chat() in a worker thread ---
        # chat() is the only UniversalAIClient method that accepts `tools=`.
        # chat_async() does NOT accept tools (so it can't do native
        # function-calling), which makes it unusable for perform_agent_chain.
        try:
            ai_resp = await asyncio.to_thread(
                self._inner.chat,
                ai_messages,
                tools=tools,
            )
        except TypeError:
            # Fallback: some duck-typed clients (test doubles) accept
            # `tools` positionally but not as a kwarg. Try positional.
            ai_resp = await asyncio.to_thread(
                self._inner.chat,
                ai_messages,
                0.7,    # temperature
                4096,   # max_tokens
                False,  # stream
                tools,  # tools (positional)
            )

        # --- Output conversion: universal.AIResponse → base.LLMResponse ---
        base_tool_calls: list[ToolCall] = []
        for utc in (ai_resp.tool_calls or []):
            # universal.ToolCall.arguments is a Dict; base.ToolCall.arguments
            # is a JSON-encoded str. Convert via json.dumps so the agent
            # chain's executor.execute(name, arguments: str, ...) receives
            # the expected JSON string.
            args = utc.arguments
            if isinstance(args, dict):
                args_str = json.dumps(args, ensure_ascii=False, default=str)
            elif isinstance(args, str):
                # Already a JSON string — validate it round-trips.
                try:
                    json.loads(args)
                    args_str = args
                except (TypeError, ValueError):
                    args_str = json.dumps({"raw": args})
            else:
                args_str = json.dumps({"raw": str(args)}, default=str)

            # universal.ToolCall.id may be "" when the provider omits it;
            # base.ToolCall.id has a default factory — fill it in.
            tc_id = utc.id or f"call_{uuid.uuid4().hex[:24]}"
            base_tool_calls.append(
                ToolCall(id=tc_id, name=utc.name, arguments=args_str)
            )

        return LLMResponse(
            content=ai_resp.content or "",
            tool_calls=base_tool_calls,
            reasoning=None,
            info={
                "model": ai_resp.model,
                "usage": ai_resp.usage,
                "raw_response": ai_resp.raw_response or {},
            },
        )


__all__ = ["UniversalAIClientAdapter"]
