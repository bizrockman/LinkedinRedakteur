"""SocialPublisher port — abstracts LinkedIn (later: X, Threads, etc.)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class PublishResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    external_id: str
    url: str | None = None


@runtime_checkable
class SocialPublisher(Protocol):
    @property
    def platform(self) -> str: ...

    async def publish(
        self,
        *,
        text: str,
        image_url: str | None = None,
    ) -> PublishResult: ...
