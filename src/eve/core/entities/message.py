"""Message entity — input from any messaging channel."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MessageSource(StrEnum):
    TELEGRAM = "telegram"
    CLI = "cli"
    WEB = "web"
    SYSTEM = "system"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Attachment(BaseModel):
    """A file attached to an incoming message."""

    model_config = ConfigDict(frozen=True)

    mime_type: str
    url: str | None = None
    original_name: str | None = None
    extracted_text: str | None = None


class IncomingMessage(BaseModel):
    """A raw incoming message from a channel — ready to feed into the agent."""

    model_config = ConfigDict(frozen=True)

    source: MessageSource
    session_id: str
    user_id: str
    chat_id: str                  # für Router-Reply (z.B. Telegram-chat_id, "stdout" für CLI)
    user_display_name: str | None = None
    text: str = ""
    attachments: list[Attachment] = Field(default_factory=list)
    received_at: datetime = Field(default_factory=datetime.utcnow)
    raw: dict = Field(default_factory=dict)


class OutgoingMessage(BaseModel):
    """Eve's Antwort — wird vom MessageRouter zum richtigen Channel geroutet.

    Übernimmt source + chat_id von der IncomingMessage, sodass Antwort
    immer auf demselben Channel landet auf dem die Anfrage kam.
    """

    model_config = ConfigDict(frozen=True)

    source: MessageSource
    chat_id: str
    text: str
    image_url: str | None = None
    reply_to: str | None = None   # Telegram-message_id für Threading

    @classmethod
    def reply_to_message(
        cls, incoming: IncomingMessage, *, text: str, image_url: str | None = None
    ) -> OutgoingMessage:
        return cls(
            source=incoming.source,
            chat_id=incoming.chat_id,
            text=text,
            image_url=image_url,
        )


class ChatTurn(BaseModel):
    """A single turn stored in chat history."""

    model_config = ConfigDict(frozen=False)

    session_id: str
    source: MessageSource
    role: MessageRole
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None
