"""WizardState — laufende Sammlung über alle Steps."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from eve.core.entities import ClientProfile, LinkedInProfileSnapshot, StoredPost


class WizardState(BaseModel):
    """Aggregierter State, den jeder Step liest/schreibt."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    profile_id: str
    use_scraper: bool = False
    linkedin_url: str | None = None
    snapshot: LinkedInProfileSnapshot | None = None
    profile: ClientProfile = Field(default_factory=ClientProfile)
    stored_posts: list[StoredPost] = Field(default_factory=list)
