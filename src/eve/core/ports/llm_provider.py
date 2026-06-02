"""LLMProvider port — provider-agnostic LLM interface."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any, Protocol, runtime_checkable

from eve.core.entities import LLMMessage, LLMResponse

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]


@runtime_checkable
class LLMProvider(Protocol):
    """A unified interface for chat-based LLMs.

    Adapters (AnthropicProvider, OpenAIProvider, OpenRouterProvider) implement
    this. The agent code never imports an SDK directly.
    """

    @property
    def name(self) -> str:
        """Short name like 'anthropic', 'openai', 'openrouter'."""
        ...

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        # None = Provider-Default verwenden. Manche Modelle (z.B. Claude Opus
        # 4.7 mit extended thinking) akzeptieren `temperature` nicht mehr.
        temperature: float | None = None,
        max_tokens: int = 4096,
        # Provider-specific extras (e.g. OpenRouter `provider` routing).
        extra: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Single-turn completion. Returns full response."""
        ...

    async def stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int = 4096,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream text deltas. Implementations should yield content chunks."""
        ...

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
        max_tokens: int = 4096,
        extra: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Multi-Step-Loop: complete → if tool_calls → execute → feed back → repeat.

        Returns the *final* assistant response (without tool_calls).

        Provider-spezifisch — Adapter implementiert die Tool-Use-Konvention
        des jeweiligen APIs (Anthropic: tool_use/tool_result blocks).
        """
        ...
