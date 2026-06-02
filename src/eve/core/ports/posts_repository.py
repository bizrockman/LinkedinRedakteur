"""PostsRepository port — Persistenz für Eves Editorial + historisches Archiv.

Wird heute von zwei Adaptern implementiert:
- `FilesystemPostsRepository`  — Wrapper um den JSON-Sidecar
- `SupabasePostsRepository`    — gegen `eve_posts` via supabase-py

Der Container entscheidet zur Laufzeit, welcher Adapter aktiv ist (Supabase
wenn voll konfiguriert, sonst Filesystem als Fallback).
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable
from uuid import UUID

from eve.core.entities import PostStatus, StoredPost


@runtime_checkable
class PostsRepository(Protocol):
    """Abstraktes Posts-Repository — Wizard, Agent und Scheduler nutzen dies."""

    async def create(self, post: StoredPost) -> StoredPost: ...

    async def get(self, post_id: UUID) -> StoredPost | None: ...

    async def update(self, post: StoredPost) -> StoredPost: ...

    async def delete(self, post_id: UUID) -> None: ...

    async def list_all(self, profile_id: str) -> list[StoredPost]: ...

    async def bulk_save(
        self, posts: list[StoredPost], *, profile_id: str
    ) -> None:
        """Komplett-Save für Bulk-Import (z.B. Wizard-Onboarding)."""
        ...

    async def search(
        self,
        *,
        profile_id: str,
        query: str | None = None,
        status: PostStatus | None = None,
        limit: int = 50,
    ) -> list[StoredPost]: ...

    async def find_due(
        self, *, profile_id: str, on_day: date
    ) -> list[StoredPost]:
        """Posts mit `status=ready` und `scheduled_for` an dem Tag."""
        ...
