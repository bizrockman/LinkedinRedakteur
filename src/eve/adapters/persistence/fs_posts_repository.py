"""FilesystemPostsRepository — wrapt den JSON-Sidecar des PromptRepository.

Fallback wenn Supabase nicht konfiguriert ist. Verhält sich nach außen
identisch zum SupabasePostsRepository — alle Methoden des PostsRepository
Protocols werden gegen `prompts/profiles/<profile_id>.posts.json` umgesetzt.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from eve.core.entities import PostStatus, StoredPost
from eve.core.ports import PromptRepository


class FilesystemPostsRepository:
    """PostsRepository-Impl gegen den existierenden Sidecar.

    Posts werden weiterhin in `prompts/profiles/<profile_id>.posts.json`
    gespeichert. Die `profile_id`-Spalte wird beim Laden aus dem Dateinamen
    rekonstruiert.
    """

    def __init__(self, prompts: PromptRepository) -> None:
        self._prompts = prompts

    async def create(self, post: StoredPost) -> StoredPost:
        if not post.profile_id:
            raise ValueError("post.profile_id darf nicht leer sein")
        if post.created_at is None:
            post.created_at = datetime.utcnow()
        existing = await self._load(post.profile_id)
        existing.append(post)
        await self._prompts.save_posts(existing, profile_id=post.profile_id)
        return post

    async def get(self, post_id: UUID) -> StoredPost | None:
        # FS-Sidecar ist profile-scoped — wir scannen alle Profile-Files
        for profile_id in await self._prompts.list_profiles():
            posts = await self._load(profile_id)
            for p in posts:
                if p.id == post_id:
                    return p
        return None

    async def update(self, post: StoredPost) -> StoredPost:
        all_posts = await self._load(post.profile_id)
        for i, existing in enumerate(all_posts):
            if existing.id == post.id:
                post.updated_at = datetime.utcnow()
                all_posts[i] = post
                await self._prompts.save_posts(all_posts, profile_id=post.profile_id)
                return post
        raise KeyError(f"Post id={post.id} nicht in profile_id={post.profile_id}")

    async def delete(self, post_id: UUID) -> None:
        for profile_id in await self._prompts.list_profiles():
            posts = await self._load(profile_id)
            filtered = [p for p in posts if p.id != post_id]
            if len(filtered) != len(posts):
                await self._prompts.save_posts(filtered, profile_id=profile_id)
                return

    async def list_all(self, profile_id: str) -> list[StoredPost]:
        return await self._load(profile_id)

    async def bulk_save(self, posts: list[StoredPost], *, profile_id: str) -> None:
        for p in posts:
            if not p.profile_id:
                p.profile_id = profile_id
        await self._prompts.save_posts(posts, profile_id=profile_id)

    async def search(
        self,
        *,
        profile_id: str,
        query: str | None = None,
        status: PostStatus | None = None,
        limit: int = 50,
    ) -> list[StoredPost]:
        posts = await self._load(profile_id)
        if status is not None:
            posts = [p for p in posts if p.status == status]
        if query:
            q = query.lower()
            posts = [p for p in posts if q in p.text.lower()]
        posts.sort(key=lambda p: p.posted_at or datetime.min, reverse=True)
        return posts[:limit]

    async def find_due(
        self, *, profile_id: str, on_day: date
    ) -> list[StoredPost]:
        posts = await self._load(profile_id)
        return [
            p
            for p in posts
            if p.status == PostStatus.READY
            and p.scheduled_for is not None
            and p.scheduled_for.date() == on_day
        ]

    # ------------------------------------------------------------------
    async def _load(self, profile_id: str) -> list[StoredPost]:
        posts = await self._prompts.load_posts(profile_id)
        # Profile_id aus Dateinamen rückübertragen wenn fehlt
        for p in posts:
            if not p.profile_id:
                p.profile_id = profile_id
        return posts
