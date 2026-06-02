"""SupabasePostsRepository — PostsRepository gegen `public.eve_posts`.

Schreibt/liest direkt via supabase-py. Die meisten Standard-Felder mappen
auf eigene Spalten, alles andere wandert in `metadata` JSONB.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from supabase import Client

from eve.core.entities import PostSource, PostStatus, StoredPost

log = logging.getLogger(__name__)

TABLE_NAME = "eve_posts"

# Standard-Spalten in eve_posts (Migration 0001). Alles andere → metadata.
DB_COLUMNS = {
    "id", "profile_id", "text", "status", "source",
    "scheduled_for", "posted_at",
    "creative_url", "linkedin_url",
    "metadata", "created_at", "updated_at",
}

# Felder von StoredPost, die NICHT als eigene Spalte existieren → metadata
METADATA_FIELDS = (
    "imported_at", "linkedin_post_id", "creative_prompt",
    "topic_tags", "engagement", "persona_score", "persona_feedback",
    "created_by", "error_message",
)


class SupabasePostsRepository:
    """PostsRepository gegen `eve_posts`.

    supabase-py ist synchron — wir wrappen alle Calls in asyncio.to_thread,
    damit der Event-Loop nicht blockiert wird.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # PostsRepository Protocol
    # ------------------------------------------------------------------
    async def create(self, post: StoredPost) -> StoredPost:
        if not post.profile_id:
            raise ValueError("post.profile_id darf nicht leer sein")
        if post.created_at is None:
            post.created_at = datetime.now(UTC)
        record = self._post_to_row(post)
        result = await asyncio.to_thread(
            lambda: self._client.table(TABLE_NAME).insert(record).execute()
        )
        if not result.data:
            raise RuntimeError(f"Supabase insert lieferte keine Daten zurück: {result}")
        return self._row_to_post(result.data[0])

    async def get(self, post_id: UUID) -> StoredPost | None:
        result = await asyncio.to_thread(
            lambda: self._client.table(TABLE_NAME)
            .select("*")
            .eq("id", str(post_id))
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return self._row_to_post(result.data[0])

    async def update(self, post: StoredPost) -> StoredPost:
        record = self._post_to_row(post)
        # id darf bei UPDATE nicht im SET sein — Supabase mag das nicht
        record.pop("id", None)
        record.pop("created_at", None)
        result = await asyncio.to_thread(
            lambda: self._client.table(TABLE_NAME)
            .update(record)
            .eq("id", str(post.id))
            .execute()
        )
        if not result.data:
            raise KeyError(f"Post id={post.id} nicht gefunden")
        return self._row_to_post(result.data[0])

    async def delete(self, post_id: UUID) -> None:
        await asyncio.to_thread(
            lambda: self._client.table(TABLE_NAME)
            .delete()
            .eq("id", str(post_id))
            .execute()
        )

    async def list_all(self, profile_id: str) -> list[StoredPost]:
        result = await asyncio.to_thread(
            lambda: self._client.table(TABLE_NAME)
            .select("*")
            .eq("profile_id", profile_id)
            .order("created_at", desc=True)
            .execute()
        )
        return [self._row_to_post(r) for r in result.data]

    async def bulk_save(self, posts: list[StoredPost], *, profile_id: str) -> None:
        """Upsert via on_conflict=linkedin_url, fallback insert."""
        if not posts:
            return
        rows = []
        for p in posts:
            if not p.profile_id:
                p.profile_id = profile_id
            rows.append(self._post_to_row(p))

        # Idempotent: bei gleicher (profile_id, linkedin_url) wird upsert'ed
        await asyncio.to_thread(
            lambda: self._client.table(TABLE_NAME)
            .upsert(rows, on_conflict="profile_id,linkedin_url", ignore_duplicates=False)
            .execute()
        )

    async def search(
        self,
        *,
        profile_id: str,
        query: str | None = None,
        status: PostStatus | None = None,
        limit: int = 50,
    ) -> list[StoredPost]:
        def _query():
            q = self._client.table(TABLE_NAME).select("*").eq("profile_id", profile_id)
            if status is not None:
                q = q.eq("status", status.value)
            if query:
                q = q.ilike("text", f"%{query}%")
            return q.order("posted_at", desc=True).limit(limit).execute()

        result = await asyncio.to_thread(_query)
        return [self._row_to_post(r) for r in result.data]

    async def find_due(
        self, *, profile_id: str, on_day: date
    ) -> list[StoredPost]:
        # scheduled_for liegt in [on_day, on_day+1) — RFC3339
        start = datetime.combine(on_day, datetime.min.time(), tzinfo=UTC).isoformat()
        end = datetime.combine(on_day, datetime.max.time(), tzinfo=UTC).isoformat()

        result = await asyncio.to_thread(
            lambda: self._client.table(TABLE_NAME)
            .select("*")
            .eq("profile_id", profile_id)
            .eq("status", PostStatus.READY.value)
            .gte("scheduled_for", start)
            .lte("scheduled_for", end)
            .execute()
        )
        return [self._row_to_post(r) for r in result.data]

    # ------------------------------------------------------------------
    # Row ↔ StoredPost Mapping
    # ------------------------------------------------------------------
    @staticmethod
    def _post_to_row(post: StoredPost) -> dict[str, Any]:
        """StoredPost → Row für eve_posts.

        Nicht-Standard-Felder wandern in `metadata` JSONB.
        """
        # Standard-Spalten
        row: dict[str, Any] = {
            "id": str(post.id),
            "profile_id": post.profile_id,
            "text": post.text,
            "status": post.status.value,
            "source": post.source.value,
            "scheduled_for": post.scheduled_for.isoformat() if post.scheduled_for else None,
            "posted_at": post.posted_at.isoformat() if post.posted_at else None,
            "creative_url": post.creative_url,
            "linkedin_url": post.linkedin_url,
        }

        # Metadata: explizit gesetztes + alle "metadata-Felder" mergen
        meta: dict[str, Any] = dict(post.metadata or {})
        for field in METADATA_FIELDS:
            value = getattr(post, field, None)
            if value is None:
                continue
            if isinstance(value, datetime):
                meta[field] = value.isoformat()
            elif isinstance(value, list | dict | int | float | str | bool):
                meta[field] = value
            else:
                meta[field] = str(value)

        row["metadata"] = meta
        return row

    @staticmethod
    def _row_to_post(row: dict[str, Any]) -> StoredPost:
        """Row aus eve_posts → StoredPost. Metadata-Felder werden wieder ausgepackt."""
        meta = row.get("metadata") or {}

        def _parse_dt(value: Any) -> datetime | None:
            if not value:
                return None
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(value.replace("Z", "+00:00"))

        # Metadata-Fields wieder zu Top-Level extrahieren (ohne sie aus meta zu poppen,
        # damit beim nächsten Save nichts verloren geht)
        kwargs: dict[str, Any] = {
            "id": UUID(row["id"]),
            "profile_id": row["profile_id"],
            "text": row["text"],
            "status": PostStatus(row["status"]),
            "source": PostSource(row["source"]),
            "scheduled_for": _parse_dt(row.get("scheduled_for")),
            "posted_at": _parse_dt(row.get("posted_at")),
            "creative_url": row.get("creative_url"),
            "linkedin_url": row.get("linkedin_url"),
            "metadata": dict(meta),
            "created_at": _parse_dt(row.get("created_at")),
            "updated_at": _parse_dt(row.get("updated_at")),
        }
        # Optionale metadata-Felder
        for field in METADATA_FIELDS:
            if field in meta:
                value = meta[field]
                if field in ("imported_at",) and isinstance(value, str):
                    kwargs[field] = _parse_dt(value)
                else:
                    kwargs[field] = value

        return StoredPost(**kwargs)
