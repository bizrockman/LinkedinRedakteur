"""ChatMemory port — persistent multi-turn conversation storage."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from eve.core.entities import ChatTurn


@runtime_checkable
class ChatMemory(Protocol):
    """Persistent memory keyed by session_id."""

    async def append(self, turn: ChatTurn) -> None: ...

    async def load(self, session_id: str, *, limit: int = 50) -> list[ChatTurn]:
        """Return the last `limit` turns in chronological order (oldest first)."""
        ...

    async def clear(self, session_id: str) -> None: ...
