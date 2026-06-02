"""LLM-level message types — provider-agnostic representation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LLMRole = Literal["system", "user", "assistant", "tool"]


class LLMMessage(BaseModel):
    """A single message in an LLM conversation, provider-agnostic."""

    model_config = ConfigDict(frozen=True)

    role: LLMRole
    content: str
    # For tool/function results
    tool_call_id: str | None = None
    name: str | None = None


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """A provider-agnostic LLM response."""

    model_config = ConfigDict(frozen=True)

    content: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str
    usage: dict[str, int] = Field(default_factory=dict)
    finish_reason: str | None = None
    raw: dict = Field(default_factory=dict)
