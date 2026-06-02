"""Post entity — represents a LinkedIn post in the editorial plan."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class PostStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    POSTED = "posted"
    ERROR = "error"
    ARCHIVED = "archived"


class Post(BaseModel):
    model_config = ConfigDict(frozen=False, use_enum_values=False)

    id: UUID = Field(default_factory=uuid4)
    text: str
    status: PostStatus = PostStatus.DRAFT
    scheduled_for: datetime | None = None
    posted_at: datetime | None = None
    creative_url: str | None = None
    creative_prompt: str | None = None
    persona_score: float | None = None
    persona_feedback: str | None = None
    linkedin_post_id: str | None = None
    error_message: str | None = None
    created_by: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
