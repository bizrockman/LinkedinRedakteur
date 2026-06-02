"""SupabaseStorageAdapter — FileStorage Protocol gegen Supabase Storage REST.

Lädt + speichert Binary-Blobs. Genutzt vom GenerateImageTool zum
Persistieren von fal.ai-Output in unserem Bucket.
"""

from __future__ import annotations

import asyncio
import logging

from supabase import Client

log = logging.getLogger(__name__)


class SupabaseStorageAdapter:
    """FileStorage-Impl via supabase-py."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def upload(
        self,
        *,
        bucket: str,
        path: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """Upload + return public URL."""
        def _do_upload():
            self._client.storage.from_(bucket).upload(
                path,
                data,
                file_options={"content-type": content_type, "upsert": "true"},
            )
            return self._client.storage.from_(bucket).get_public_url(path)

        url = await asyncio.to_thread(_do_upload)
        log.info("Uploaded %d bytes to %s/%s", len(data), bucket, path)
        return url

    async def delete(self, *, bucket: str, path: str) -> None:
        await asyncio.to_thread(
            lambda: self._client.storage.from_(bucket).remove([path])
        )
