"""generate_image-Tool — wrappt fal.ai für den Eve-Agent.

Tools-Beschreibung is in Englisch um eindeutig den fal.ai-Modell-Sprach-Kontext
zu adressieren — der Image-Prompt wird auf Englisch formuliert (für bestere
Resultate bei Seedream / Nano Banana). Eve schreibt deutsche Posts aber
englische Image-Prompts.
"""

from __future__ import annotations

import logging
from typing import Any

from eve.agent.tools.base import ToolDefinition
from eve.core.ports import ImageGenerator

log = logging.getLogger(__name__)


class GenerateImageTool:
    """Generiert ein Bild für den aktuellen Post via fal.ai."""

    def __init__(self, generator: ImageGenerator) -> None:
        self.generator = generator

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
        return (
            f"✓ Bild generiert.\n"
            f"  URL:        {result.url}\n"
            f"  Modell:     {result.model}\n"
            f"  References: {ref_count}\n"
            "\n"
            "Übergib diese URL als `creative_url` an `create_post`."
        )
