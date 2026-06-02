"""SupabaseChatMemory — ChatMemory gegen `public.eve_chat_histories`.

Persistiert Multi-Turn-History so dass sie über Process-Restarts hinweg
erhalten bleibt — Pendant zum n8n `Postgres Chat Memory` Node.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from supabase import Client

from eve.core.entities import ChatTurn, MessageRole, MessageSource

log = logging.getLogger(__name__)

TABLE_NAME = "eve_chat_histories"


class SupabaseChatMemory:
    """ChatMemory-Protocol-Impl, persistent via Supabase."""

    def __init__(self, client: Client, *, profile_id: str) -> None:
        self._client = client
        self._profile_id = profile_id

    async def append(self, turn: ChatTurn) -> None:
        if turn.created_at is None:
            turn.created_at = datetime.now(UTC)
        row = {
            "session_id": turn.session_id,
            "profile_id": self._profile_id,
            "source": turn.source.value,
            "role": turn.role.value,
            "content": turn.content,
            "metadata": turn.metadata or {},
        }
        await asyncio.to_thread(
            lambda: self._client.table(TABLE_NAME).insert(row).execute()
        )

    async def load(self, session_id: str, *, limit: int = 50) -> list[ChatTurn]:
        # Wir wollen die *letzten* limit Turns chronologisch (älteste zuerst)
        def _query():
            return (
                self._client.table(TABLE_NAME)
                .select("*")
                .eq("session_id", session_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

        result = await asyncio.to_thread(_query)
        rows = result.data or []
        # desc → wir wollen asc fürs Replay
        rows.reverse()
        return [self._row_to_turn(r) for r in rows]

    async def clear(self, session_id: str) -> None:
        await asyncio.to_thread(
            lambda: self._client.table(TABLE_NAME)
            .delete()
            .eq("session_id", session_id)
            .execute()
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_turn(row: dict) -> ChatTurn:
        created = row.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return ChatTurn(
            session_id=row["session_id"],
            source=MessageSource(row["source"]),
            role=MessageRole(row["role"]),
            content=row["content"],
            metadata=row.get("metadata") or {},
            created_at=created,
        )
