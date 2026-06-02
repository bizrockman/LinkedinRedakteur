"""Tests für MessageRouter."""

from __future__ import annotations

import pytest

from eve.core.entities import IncomingMessage, MessageSource, OutgoingMessage
from eve.use_cases.message_router import MessageRouter


class FakeMessagingProvider:
    """Test-Stub der MessagingProvider Protocol erfüllt."""

    def __init__(self, source: MessageSource) -> None:
        self._source = source
        self.sent_texts: list[tuple[str, str]] = []
        self.sent_images: list[tuple[str, str, str | None]] = []

    @property
    def source(self) -> MessageSource:
        return self._source

    async def send_text(self, *, chat_id: str, text: str, reply_to: str | None = None) -> None:
        self.sent_texts.append((chat_id, text))

    async def send_image(
        self,
        *,
        chat_id: str,
        image_url: str,
        caption: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        self.sent_images.append((chat_id, image_url, caption))


async def test_dispatch_routes_to_correct_provider():
    cli_provider = FakeMessagingProvider(MessageSource.CLI)
    tg_provider = FakeMessagingProvider(MessageSource.TELEGRAM)
    router = MessageRouter()
    router.register(cli_provider)
    router.register(tg_provider)

    await router.dispatch(
        OutgoingMessage(source=MessageSource.CLI, chat_id="stdout", text="hi cli")
    )
    await router.dispatch(
        OutgoingMessage(source=MessageSource.TELEGRAM, chat_id="123", text="hi tg")
    )

    assert cli_provider.sent_texts == [("stdout", "hi cli")]
    assert tg_provider.sent_texts == [("123", "hi tg")]


async def test_dispatch_with_image():
    cli_provider = FakeMessagingProvider(MessageSource.CLI)
    router = MessageRouter()
    router.register(cli_provider)

    await router.dispatch(
        OutgoingMessage(
            source=MessageSource.CLI,
            chat_id="stdout",
            text="caption",
            image_url="https://example.com/img.png",
        )
    )
    assert cli_provider.sent_images == [("stdout", "https://example.com/img.png", "caption")]
    assert cli_provider.sent_texts == []


async def test_dispatch_unknown_source_raises():
    router = MessageRouter()
    with pytest.raises(KeyError, match="Kein MessagingProvider"):
        await router.dispatch(
            OutgoingMessage(source=MessageSource.WEB, chat_id="x", text="lost")
        )


async def test_is_registered_and_listing():
    router = MessageRouter()
    assert not router.is_registered(MessageSource.CLI)
    router.register(FakeMessagingProvider(MessageSource.CLI))
    assert router.is_registered(MessageSource.CLI)
    assert MessageSource.CLI in router.registered_sources()


async def test_outgoing_reply_helper_inherits_routing():
    incoming = IncomingMessage(
        source=MessageSource.TELEGRAM,
        session_id="TG_42",
        user_id="42",
        chat_id="-100123",
        text="Hi Eve",
    )
    reply = OutgoingMessage.reply_to_message(incoming, text="Hi back")
    assert reply.source == MessageSource.TELEGRAM
    assert reply.chat_id == "-100123"
    assert reply.text == "Hi back"
