"""MessagingProvider port — abstracts Telegram/Slack/Mattermost/etc."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from eve.core.entities import MessageSource


@runtime_checkable
class MessagingProvider(Protocol):
    """Outbound side: send a message back to the user/channel."""

    @property
    def source(self) -> MessageSource: ...

    async def send_text(self, *, chat_id: str, text: str, reply_to: str | None = None) -> None: ...

    async def send_image(
        self,
        *,
        chat_id: str,
        image_url: str,
        caption: str | None = None,
        reply_to: str | None = None,
    ) -> None: ...
