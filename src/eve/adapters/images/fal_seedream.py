"""fal.ai Seedream v4.5 Image-Generator.

Folgt dem fal.ai Queue-Pattern (drei Calls):

  1. POST  queue.fal.run/<model>           → status_url + response_url
  2. Poll  GET status_url alle 5s          bis status == "COMPLETED"
  3. GET   response_url                    → image URL

Referenz-Bilder (für konsistente Identität) werden bei jedem Call frisch aus
dem Supabase-Storage gelistet (`<bucket>/<references_path>/`). Wenn keine
gefunden werden, läuft die Generierung trotzdem — nur ohne Identitäts-Anker.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from eve.core.ports.image_generator import GeneratedImage

log = logging.getLogger(__name__)

QUEUE_BASE_URL = "https://queue.fal.run"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


class FalSeedreamGenerator:
    """Implementiert ImageGenerator Protocol via fal.ai Seedream v4.5."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "fal-ai/bytedance/seedream/v4.5/edit",
        supabase_client=None,
        bucket: str = "eve-media",
        references_path: str = "references",
        poll_interval_seconds: float = 5.0,
        max_wait_seconds: int = 300,
        request_timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.supabase_client = supabase_client
        self.bucket = bucket
        self.references_path = references_path
        self.poll_interval_seconds = poll_interval_seconds
        self.max_wait_seconds = max_wait_seconds
        self.request_timeout_seconds = request_timeout_seconds

    async def generate(
        self,
        *,
        prompt: str,
        reference_image_urls: list[str] | None = None,
        size: str = "square_hd",
    ) -> GeneratedImage:
        urls = reference_image_urls
        if urls is None and self.supabase_client is not None:
            urls = self.list_references()
        urls = urls or []

        if not urls:
            log.warning(
                "Keine Reference-Bilder verfügbar — fal.ai läuft, aber ohne "
                "Identitäts-Anker (Output kann je nach Lauf abweichen)."
            )

        headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt,
            "image_size": size,
            "image_urls": urls,
        }

        log.info("fal.ai payload: %d image_urls, prompt %d chars", len(urls), len(prompt))
        for i, u in enumerate(urls):
            log.debug("  image_urls[%d] = %s", i, u)

        async with httpx.AsyncClient(timeout=self.request_timeout_seconds) as client:
            submission = await self._submit(client, headers, payload)
            log.info(
                "fal.ai accepted — request_id=%s, %d refs sent",
                submission.get("request_id"),
                len(urls),
            )

            status_data = await self._poll(client, headers, submission["status_url"])
            data = await self._fetch_result(client, headers, submission["response_url"])

            images = data.get("images", [])
            if not images:
                raise RuntimeError(f"fal.ai response has no images: {data}")
            first = images[0]

            return GeneratedImage(
                url=first["url"],
                prompt=prompt,
                model=self.model,
                metadata={
                    "reference_count": len(urls),
                    "reference_urls": list(urls),  # was wir wirklich gesendet haben
                    "request_id": submission.get("request_id"),
                    "final_status": status_data.get("status"),
                    "fal_raw": data,
                },
            )

    # ------------------------------------------------------------------
    # Queue-Schritte
    # ------------------------------------------------------------------
    async def _submit(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        payload: dict,
    ) -> dict:
        r = await client.post(f"{QUEUE_BASE_URL}/{self.model}", headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(
                f"fal.ai submit failed ({r.status_code}): {r.text[:500]}"
            )
        return r.json()

    async def _poll(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        status_url: str,
    ) -> dict:
        waited = 0.0
        while waited < self.max_wait_seconds:
            await asyncio.sleep(self.poll_interval_seconds)
            waited += self.poll_interval_seconds

            r = await client.get(status_url, headers=headers)
            if r.status_code >= 400:
                raise RuntimeError(
                    f"fal.ai status poll failed ({r.status_code}): {r.text[:500]}"
                )
            data = r.json()
            status = data.get("status")
            log.debug("fal.ai status=%s after %.1fs", status, waited)

            if status == "COMPLETED":
                return data
            if status in ("IN_QUEUE", "IN_PROGRESS"):
                continue
            raise RuntimeError(f"fal.ai returned unexpected status: {data}")

        raise TimeoutError(
            f"fal.ai noch nicht fertig nach {self.max_wait_seconds}s — abgebrochen"
        )

    async def _fetch_result(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        response_url: str,
    ) -> dict:
        r = await client.get(response_url, headers=headers)
        if r.status_code >= 400:
            raise RuntimeError(
                f"fal.ai result fetch failed ({r.status_code}): {r.text[:500]}"
            )
        return r.json()

    # ------------------------------------------------------------------
    # Reference-Listing
    # ------------------------------------------------------------------
    def list_references(self) -> list[str]:
        """Listet alle Bild-Files in `<bucket>/<references_path>/`.

        Liefert leere Liste falls Folder nicht existiert oder leer ist.
        """
        if self.supabase_client is None:
            return []
        try:
            files = self.supabase_client.storage.from_(self.bucket).list(self.references_path)
        except Exception as e:
            log.warning("References-Listing fehlgeschlagen: %s", e)
            return []

        urls: list[str] = []
        storage = self.supabase_client.storage.from_(self.bucket)
        for f in files:
            name = f.get("name", "")
            if name.startswith(".") or not name.lower().endswith(IMAGE_EXTENSIONS):
                continue
            url = storage.get_public_url(f"{self.references_path}/{name}")
            urls.append(url)
        log.info(
            "References geladen: %d Bilder aus %s/%s",
            len(urls), self.bucket, self.references_path,
        )
        return urls
