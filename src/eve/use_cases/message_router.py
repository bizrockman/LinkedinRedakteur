"""MessageRouter — routet Eve's Antworten zum ursprünglichen Channel.

Pattern: source-Feld der OutgoingMessage als Routing-Schlüssel. Eve selbst
ist channel-agnostisch — Telegram, CLI und (später) Web reagieren je auf
ihre eigenen IncomingMessages und Eve antwortet, der Router stellt zu.

Beispiel-Setup:
    router = MessageRouter()
    router.register(CLIMessenger(console))
    router.register(TelegramMessenger(bot))
    ...
    await router.dispatch(OutgoingMessage(source=..., chat_id=..., text=...))
"""

from __future__ import annotations

import logging

from eve.core.entities import MessageSource, OutgoingMessage
from eve.core.ports import MessagingProvider

log = logging.getLogger(__name__)


class MessageRouter:
    """Dispatcher von OutgoingMessages an die richtigen MessagingProvider."""

    def __init__(self) -> None:
        self._providers: dict[MessageSource, MessagingProvider] = {}

    def register(self, provider: MessagingProvider) -> None:
        """Registriert einen Provider unter seiner source-Identifikation."""
        self._providers[provider.source] = provider
        log.info("MessageRouter: registered %s provider", provider.source)

    def is_registered(self, source: MessageSource) -> bool:
        return source in self._providers

    def registered_sources(self) -> list[MessageSource]:
        return list(self._providers.keys())

    async def dispatch(self, message: OutgoingMessage) -> None:
        """Sendet die Antwort zum passenden Channel.

        Wirft KeyError wenn kein Provider für die source registriert ist.
        """
        provider = self._providers.get(message.source)
        if provider is None:
            raise KeyError(
                f"Kein MessagingProvider für source={message.source!r} registriert. "
                f"Verfügbar: {self.registered_sources()}"
            )

        if message.image_url:
            await provider.send_image(
                chat_id=message.chat_id,
                image_url=message.image_url,
                caption=message.text or None,
                reply_to=message.reply_to,
            )
        else:
            await provider.send_text(
                chat_id=message.chat_id,
                text=message.text,
                reply_to=message.reply_to,
            )
