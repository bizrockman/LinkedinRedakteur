"""ImageGenerator port — abstracts fal.ai, OpenAI Images, Replicate, etc."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class GeneratedImage(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    prompt: str
    model: str
    metadata: dict = {}


@runtime_checkable
class ImageGenerator(Protocol):
    """Async image generation. Implementations handle queue/polling internally."""

    async def generate(
        self,
        *,
        prompt: str,
        reference_image_urls: list[str] | None = None,
        size: str = "square_hd",
    ) -> GeneratedImage: ...
