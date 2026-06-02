"""FileStorage port — abstracts Supabase Storage / S3 / local disk."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class FileStorage(Protocol):
    """Upload binary blobs and return a publicly accessible URL."""

    async def upload(
        self,
        *,
        bucket: str,
        path: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """Returns a URL to the uploaded file."""
        ...

    async def delete(self, *, bucket: str, path: str) -> None: ...
