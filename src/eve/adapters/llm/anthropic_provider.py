"""Anthropic Claude — LLMProvider Adapter.

Maps the provider-agnostic LLMMessage / LLMResponse representation onto
Anthropic's Messages API.

Notes:
- Claude uses a separate `system` parameter (not a role="system" message)
- Tool use returns content blocks of type "tool_use", which we flatten into
  the `tool_calls` list on LLMResponse
- Streaming yields raw text deltas
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import Message

from eve.core.entities import LLMMessage, LLMResponse, ToolCall
from eve.core.ports.llm_provider import ToolExecutor

log = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 4096


def _block_to_dict(block: Any) -> dict[str, Any]:
    """Wandelt einen Anthropic Content-Block in dict für die Re-Submission.

    Wir können nicht 1:1 den Block weiterreichen — Anthropic erwartet das
    Original-Dict-Format wenn wir die Assistant-Turn re-submitten.
    """
    btype = getattr(block, "type", None)
    if btype == "text":
        return {"type": "text", "text": block.text}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": dict(block.input) if block.input else {},
        }
    # Fallback: pydantic-model_dump
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json")
    return {"type": btype or "unknown"}


class AnthropicProvider:
    """Adapter for Anthropic's Claude models.

    Implements the LLMProvider Protocol (duck-typed; we don't inherit).
    """

    name: str = "anthropic"

    def __init__(self, api_key: str, *, timeout: float = 120.0) -> None:
        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout)

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _split_messages(
        messages: Sequence[LLMMessage],
        explicit_system: str | None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Split out any role='system' messages (Claude takes them separately).

        Any explicit_system passed in by the caller takes precedence; otherwise
        we concatenate any role='system' LLMMessages.
        """
        system_parts: list[str] = []
        if explicit_system:
            system_parts.append(explicit_system)

        mapped: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
                continue
            if m.role == "tool":
                # Claude expects tool results as user-role content blocks
                mapped.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id or "",
                                "content": m.content,
                            }
                        ],
                    }
                )
                continue
            mapped.append({"role": m.role, "content": m.content})

        system = "\n\n".join(p for p in system_parts if p) or None
        return system, mapped

    @staticmethod
    def _parse_response(msg: Message) -> LLMResponse:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in msg.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text)
            elif btype == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input) if block.input else {},
                    )
                )

        usage = {}
        if msg.usage is not None:
            usage = {
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
            }

        return LLMResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            model=msg.model,
            usage=usage,
            finish_reason=msg.stop_reason,
            raw=msg.model_dump(mode="json"),
        )

    # ------------------------------------------------------------------
    # LLMProvider Protocol
    # ------------------------------------------------------------------
    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        extra: dict[str, Any] | None = None,
    ) -> LLMResponse:
        system_block, mapped = self._split_messages(messages, system)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": mapped,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if system_block:
            kwargs["system"] = system_block
        if tools:
            kwargs["tools"] = tools
        if extra:
            kwargs.update(extra)

        msg = await self._client.messages.create(**kwargs)
        return self._parse_response(msg)

    async def stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        system_block, mapped = self._split_messages(messages, system)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": mapped,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if system_block:
            kwargs["system"] = system_block
        if tools:
            kwargs["tools"] = tools
        if extra:
            kwargs.update(extra)

        async with self._client.messages.stream(**kwargs) as stream:
            async for delta in stream.text_stream:
                yield delta

    async def run_with_tools(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str,
        system: str | None = None,
        tools: list[dict[str, Any]],
        tool_executor: ToolExecutor,
        max_iterations: int = 10,
        temperature: float | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        extra: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Multi-Iteration Tool-Calling-Loop für Anthropic Claude.

        Iteriert solange wie Claude `tool_use` Blocks zurückgibt:
        1. Sendet messages an Claude
        2. Wenn response = nur text → fertig, return
        3. Wenn response = enthält tool_use → execute jedes Tool, append
           assistant-message + tool_result, weiter zu Schritt 1
        """
        system_block, mapped = self._split_messages(messages, system)
        # Wir mutieren mapped während des Loops (für die nächsten Calls)
        conv: list[dict[str, Any]] = list(mapped)
        usage_total = {"input_tokens": 0, "output_tokens": 0}
        last_msg: Message | None = None

        for iteration in range(max_iterations):
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": conv,
            }
            if temperature is not None:
                kwargs["temperature"] = temperature
            if system_block:
                kwargs["system"] = system_block
            if tools:
                kwargs["tools"] = tools
            if extra:
                kwargs.update(extra)

            msg = await self._client.messages.create(**kwargs)
            last_msg = msg

            # Usage aufsummieren
            if msg.usage is not None:
                usage_total["input_tokens"] += msg.usage.input_tokens
                usage_total["output_tokens"] += msg.usage.output_tokens

            # Tool-Use-Blocks rauspicken
            tool_use_blocks = [
                b for b in msg.content if getattr(b, "type", None) == "tool_use"
            ]

            if not tool_use_blocks:
                # Fertig — Claude hat keine weiteren Tool-Calls
                log.debug("Agent finished after %d iteration(s)", iteration + 1)
                return self._build_final_response(msg, usage_total)

            log.info(
                "Agent iter %d: %d tool_use block(s): %s",
                iteration + 1,
                len(tool_use_blocks),
                [b.name for b in tool_use_blocks],
            )

            # Assistant-Turn mit allen Content-Blocks (text + tool_use) appenden
            conv.append({"role": "assistant", "content": [_block_to_dict(b) for b in msg.content]})

            # Jedes Tool ausführen + Results sammeln
            tool_results_content: list[dict[str, Any]] = []
            for tu in tool_use_blocks:
                args = dict(tu.input) if tu.input else {}
                try:
                    result_text = await tool_executor(tu.name, args)
                    is_error = False
                except Exception as e:
                    result_text = f"Tool '{tu.name}' threw {type(e).__name__}: {e}"
                    is_error = True
                    log.exception("Tool '%s' execution failed", tu.name)

                tool_results_content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": result_text,
                        "is_error": is_error,
                    }
                )

            conv.append({"role": "user", "content": tool_results_content})

        # Max-Iterations exhausted — return last response (mit Hinweis im Content)
        log.warning("Agent hit max_iterations=%d without final response", max_iterations)
        if last_msg is None:
            raise RuntimeError("Tool-Loop endete ohne Response")
        return self._build_final_response(last_msg, usage_total)

    def _build_final_response(
        self, msg: Message, usage_total: dict[str, int]
    ) -> LLMResponse:
        text_parts: list[str] = []
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        return LLMResponse(
            content="".join(text_parts),
            tool_calls=[],  # finale Response hat per Definition keine offenen Calls mehr
            model=msg.model,
            usage=usage_total,
            finish_reason=msg.stop_reason,
            raw=msg.model_dump(mode="json"),
        )
