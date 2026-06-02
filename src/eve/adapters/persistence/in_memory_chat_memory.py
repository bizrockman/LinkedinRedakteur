"""In-Memory ChatMemory — schneller Speicher für Dev + CLI-Sessions.

Verliert beim Prozess-Ende alles. Für Production später → SupabaseChatMemory
(Tabelle `eve_chat_histories`, Migration 0002).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from eve.core.entities import ChatTurn


class InMemoryChatMemory:
    """ChatMemory Protocol — Dict-basiert, kein Persistenz."""

    def __init__(self) -> None:
        self._sessions: dict[str, list[ChatTurn]] = defaultdict(list)

    async def append(self, turn: ChatTurn) -> None:
        if turn.created_at is None:
            turn.created_at = datetime.utcnow()
        self._sessions[turn.session_id].append(turn)

    async def load(self, session_id: str, *, limit: int = 50) -> list[ChatTurn]:
        history = self._sessions.get(session_id, [])
        return history[-limit:]

    async def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
