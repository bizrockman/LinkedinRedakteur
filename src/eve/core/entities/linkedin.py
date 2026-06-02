"""LinkedIn-spezifische Scraping-Entities."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LinkedInPost(BaseModel):
    """Ein einzelner Beitrag, wie er vom Profil gescrapt wurde."""

    model_config = ConfigDict(frozen=True)

    text: str
    posted_at: datetime | None = None
    url: str | None = None
    impressions: int | None = None  # nur sichtbar bei eigenem Profil
    likes: int | None = None
    comments: int | None = None
    reposts: int | None = None
    media_urls: list[str] = Field(default_factory=list)


class AudienceDemographicEntry(BaseModel):
    """Eine einzelne Zeile in einer Audience-Demographics-Kategorie."""

    model_config = ConfigDict(frozen=True)

    label: str
    percentage: str  # bewusst als String, z.B. "9,7 %"


class AudienceDemographics(BaseModel):
    """Gesamte Demographics-Daten eines Profils.

    `categories` mappt z.B. "Jobbezeichnung" -> [Gründer:in (9,7 %), ...].
    """

    model_config = ConfigDict(frozen=True)

    categories: dict[str, list[AudienceDemographicEntry]] = Field(default_factory=dict)

    def to_paste_block(self) -> str:
        """Format für den `derive_audience` Prompt — identisch zum manuellen Paste."""
        out: list[str] = []
        for category, entries in self.categories.items():
            out.append(category)
            for e in entries:
                out.append(e.label)
                out.append(e.percentage)
            out.append("")
        return "\n".join(out).strip()


class LinkedInProfileSnapshot(BaseModel):
    """Schnappschuss eines LinkedIn-Profils zu einem Zeitpunkt."""

    model_config = ConfigDict(frozen=True)

    profile_url: str
    name: str = ""
    headline: str = ""
    about: str = ""
    location: str = ""
    follower_count: int | None = None
    connection_count: int | None = None
    posts: list[LinkedInPost] = Field(default_factory=list)
    audience: AudienceDemographics | None = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now())
    raw: dict = Field(default_factory=dict)
