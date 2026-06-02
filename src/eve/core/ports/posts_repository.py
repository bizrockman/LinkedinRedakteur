"""PostsRepository port — DAO for editorial plan posts."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable
from uuid import UUID

from eve.core.entities import Post, PostStatus


@runtime_checkable
class PostsRepository(Protocol):
    """Abstract data access for posts. Swap Supabase ↔ Baserow via this port."""

    async def create(self, post: Post) -> Post: ...

    async def get(self, post_id: UUID) -> Post | None: ...

    async def update(self, post: Post) -> Post: ...

    async def delete(self, post_id: UUID) -> None: ...

    async def search(
        self,
        *,
        status: PostStatus | None = None,
        scheduled_on: date | None = None,
        created_by: str | None = None,
        limit: int = 50,
    ) -> list[Post]: ...

    async def find_due(self, on_day: date) -> list[Post]:
        """Posts with status=ready and scheduled_for on the given day (timezone-naive day match)."""
        ...
