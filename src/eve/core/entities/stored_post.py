"""StoredPost — ein Post in der Eve-eigenen Sammlung (Editorial + Historie).

Dies ist die zukünftige `eve.posts`-Tabelle, vorerst gespeichert in einer
JSON-Sidecar-Datei pro Profil (`prompts/profiles/<id>.posts.json`).

Unterschied zu LinkedInPost: LinkedInPost ist ein Scrape-Snapshot (immutable
Quelldaten). StoredPost ist *unser* Datenmodell für die Editorial-Pipeline +
historische Archive.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eve.core.entities.post import PostStatus


class PostSource(StrEnum):
    """Wo kommt der Post her?"""

    EVE = "eve"                          # Von Eve generiert
    LINKEDIN_IMPORT = "linkedin_import"  # Playwright-Scrape (Onboarding/Refresh)
    GDPR_IMPORT = "gdpr_import"          # DSGVO-Datenexport
    MANUAL_IMPORT = "manual_import"      # User-Paste via Wizard/Chat


class StoredPost(BaseModel):
    """Ein Post in Eves Editorial+Archive-Tabelle."""

    model_config = ConfigDict(frozen=False)

    id: UUID = Field(default_factory=uuid4)
    profile_id: str = ""                 # zugeordneter Profile-Kontext (multi-tenant)
    text: str
    status: PostStatus = PostStatus.POSTED
    source: PostSource = PostSource.EVE

    # Zeitachsen
    scheduled_for: datetime | None = None
    posted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    imported_at: datetime | None = None

    # LinkedIn-Spezifika (für importierte Posts)
    linkedin_url: str | None = None
    linkedin_post_id: str | None = None  # urn:li:activity:...

    # Creative + Klassifikation
    creative_url: str | None = None
    creative_prompt: str | None = None
    topic_tags: list[str] = Field(default_factory=list)

    # Engagement (heute oft leer; pgvector + analytics später)
    engagement: dict = Field(default_factory=dict)  # {likes, comments, reposts, impressions}

    # Persona-Feedback (für Eve-generierte Posts)
    persona_score: float | None = None
    persona_feedback: str | None = None

    # Origin/Audit
    created_by: str | None = None
    error_message: str | None = None
    metadata: dict = Field(default_factory=dict)
