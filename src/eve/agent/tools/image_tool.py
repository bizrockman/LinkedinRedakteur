"""generate_image-Tool — wrappt fal.ai für den Eve-Agent.

Tools-Beschreibung is in Englisch um eindeutig den fal.ai-Modell-Sprach-Kontext
zu adressieren — der Image-Prompt wird auf Englisch formuliert (für bestere
Resultate bei Seedream / Nano Banana). Eve schreibt deutsche Posts aber
englische Image-Prompts.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import httpx

from eve.agent.tools.base import ToolDefinition
from eve.core.ports import FileStorage, ImageGenerator

log = logging.getLogger(__name__)

DEFAULT_STORAGE_PATH_PREFIX = "posts"


class GenerateImageTool:
    """Generiert ein Bild für den aktuellen Post via fal.ai.

    Wenn ein FileStorage konfiguriert ist (Supabase Storage), wird das Bild
    automatisch von fal.ai's CDN nach `<bucket>/posts/<uuid>.png` migriert —
    so überlebt es auch wenn fal.ai die Datei nach 24h löscht.
    """

    def __init__(
        self,
        generator: ImageGenerator,
        *,
        storage: FileStorage | None = None,
        bucket: str | None = None,
        storage_path_prefix: str = DEFAULT_STORAGE_PATH_PREFIX,
    ) -> None:
        self.generator = generator
        self.storage = storage
        self.bucket = bucket
        self.storage_path_prefix = storage_path_prefix

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_image",
            description=(
                "Generates an image for the current LinkedIn post via fal.ai "
                "Seedream. The user's face is preserved using reference images "
                "from Supabase Storage. "
                "\n\n"
                "WICHTIG: Den `prompt` ALWAYS auf Englisch formulieren — "
                "fal.ai funktioniert besser damit. Halte ihn detailliert: "
                "describe scene, person's action, outfit, lighting, mood, "
                "camera setup (e.g. '85mm lens, shallow depth of field'). "
                "Erwähne explizit 'the same person from the reference image' "
                "um die Identität zu erhalten."
                "\n\n"
                "Speichere danach den `prompt` mit im `create_post` als "
                "`creative_prompt` (für späteres Re-Generieren)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "Detaillierter englischer Image-Prompt. "
                            "Sollte 'the same person from the reference image' "
                            "enthalten + Szene + Outfit + Lighting."
                        ),
                    },
                    "size": {
                        "type": "string",
                        "enum": [
                            "square_hd",
                            "square",
                            "portrait_4_3",
                            "portrait_16_9",
                            "landscape_4_3",
                            "landscape_16_9",
                        ],
                        "description": (
                            "Bildformat. LinkedIn-Posts: 'square_hd' (1080x1080) "
                            "ist Standard. Für längere Reichweite 'portrait_4_3'."
                        ),
                    },
                },
                "required": ["prompt"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> str:
        prompt = args.get("prompt", "").strip()
        if not prompt:
            return "Fehler: prompt ist leer."

        size = args.get("size", "square_hd")
        log.info("GenerateImage: size=%s, prompt-chars=%d", size, len(prompt))

        try:
            result = await self.generator.generate(prompt=prompt, size=size)
        except Exception as e:
            log.exception("Image generation failed")
            return (
                f"Bildgenerierung fehlgeschlagen: {type(e).__name__}: {e}\n"
                "Du kannst den Post auch ohne Bild speichern (`create_post` ohne `creative_url`) "
                "und das Bild später nachreichen."
            )

        ref_count = result.metadata.get("reference_count", 0)
        final_url = result.url
        persisted = False

        # Wenn Storage + Bucket konfiguriert: Bild von fal.ai-CDN in unseren Bucket migrieren
        if self.storage is not None and self.bucket:
            try:
                persisted_url = await self._persist_to_storage(result.url)
                final_url = persisted_url
                persisted = True
            except Exception as e:
                log.warning("Storage-Upload fehlgeschlagen, nutze fal.ai-URL: %s", e)

        return (
            f"✓ Bild generiert.\n"
            f"  URL:        {final_url}\n"
            f"  Modell:     {result.model}\n"
            f"  References: {ref_count}\n"
            f"  Persistent: {'ja (Supabase Storage)' if persisted else 'nein (fal.ai-CDN, ~24h)'}\n"
            "\n"
            "Übergib diese URL als `creative_url` an `create_post`."
        )

    async def _persist_to_storage(self, fal_url: str) -> str:
        """Lädt das Bild von fal.ai-CDN runter, uploaded in Supabase Storage."""
        assert self.storage is not None and self.bucket is not None

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(fal_url)
            r.raise_for_status()
            image_bytes = r.content
            content_type = r.headers.get("content-type", "image/png")

        # Dateiendung aus Content-Type bestimmen
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(
            content_type.lower().split(";")[0].strip(), "png"
        )
        path = f"{self.storage_path_prefix}/{uuid4().hex}.{ext}"

        public_url = await self.storage.upload(
            bucket=self.bucket,
            path=path,
            data=image_bytes,
            content_type=content_type,
        )
        log.info(
            "Bild migriert: %d Bytes → %s/%s (%s)",
            len(image_bytes), self.bucket, path, content_type,
        )
        return public_url
