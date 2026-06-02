"""ClientProfile — alle kundenspezifischen Daten, die einen Prompt-Template füllen.

Single Source of Truth für: Agent-Identität, Kunden-Info, Themen, Zielgruppe,
erfolgreichste Posts, NoGos und Synthetic Personas.

Wird im Onboarding-Prozess erstellt und kann in YAML, Postgres oder JSON
gespeichert werden — die Storage-Form ist Sache des Adapters.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentPersonality(BaseModel):
    """Insights-Discovery-Verteilung der Agent-Persönlichkeit (Summe = 100)."""

    model_config = ConfigDict(frozen=True)

    green: int = Field(default=40, ge=0, le=100, description="unterstützend, einfühlsam")
    blue: int = Field(default=30, ge=0, le=100, description="analytisch, präzise")
    red: int = Field(default=20, ge=0, le=100, description="durchsetzungsfähig, zielorientiert")
    yellow: int = Field(default=10, ge=0, le=100, description="kommunikativ, inspirierend")


class AgentIdentity(BaseModel):
    """Wer ist der Agent? (Name, Persönlichkeit, Selbstverständnis)."""

    model_config = ConfigDict(frozen=True)

    name: str = "Eve"
    role_description: str = (
        "herausragender LinkedIn Copywriter, der Kunden geholfen hat, "
        "ihr persönliches LinkedIn-Profil auf über 50.000 Follower aufzubauen"
    )
    personality: AgentPersonality = Field(default_factory=AgentPersonality)


class SuccessfulPost(BaseModel):
    """Ein Top-Performer-Post zum Imitieren von Struktur und Stil."""

    model_config = ConfigDict(frozen=True)

    text: str
    impressions: int | None = None
    engagement: int | None = None
    note: str | None = None  # warum dieser Post gut funktioniert hat


class ClientInfo(BaseModel):
    """Der Kunde, für den geschrieben wird (Person, Profil, Themen)."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    description: str = ""  # ehemals LINKEDIN-INFOTEXT
    linkedin_url: str | None = None
    topics: list[str] = Field(default_factory=list)  # ehemals TOPIC1-5


class TargetAudience(BaseModel):
    """Wer liest die Posts? (Beschreibung + Organisation)."""

    model_config = ConfigDict(frozen=True)

    description: str = ""
    organization: str = ""


class SyntheticPersona(BaseModel):
    """Eine Persona der Zielgruppe für Feedback-Loops."""

    model_config = ConfigDict(frozen=True)

    name: str
    role: str  # vollständige Rolle / Position
    organization: str = ""
    description: str = ""  # weitere Beschreibung (Wünsche, Sorgen, Hintergrund)


class ClientProfile(BaseModel):
    """Top-level Profile-Objekt — gespeichert pro Kunde/Projekt."""

    model_config = ConfigDict(frozen=False)

    profile_id: str = "default"
    agent: AgentIdentity = Field(default_factory=AgentIdentity)
    client: ClientInfo = Field(default_factory=ClientInfo)
    audience: TargetAudience = Field(default_factory=TargetAudience)
    successful_posts: list[SuccessfulPost] = Field(default_factory=list)
    nogos: list[str] = Field(default_factory=list)
    personas: list[SyntheticPersona] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def is_complete(self) -> bool:
        """Heuristik: Sind die Pflichtfelder gefüllt, sodass die Templates renderbar sind?"""
        return bool(
            self.client.description
            and self.client.topics
            and self.audience.description
            and len(self.successful_posts) >= 1
            and len(self.personas) >= 1
        )

    def missing_fields(self) -> list[str]:
        """Welche Felder fehlen für ein vollständiges Profil?"""
        gaps: list[str] = []
        if not self.client.description:
            gaps.append("client.description")
        if not self.client.topics:
            gaps.append("client.topics")
        if not self.audience.description:
            gaps.append("audience.description")
        if not self.successful_posts:
            gaps.append("successful_posts")
        if not self.personas:
            gaps.append("personas")
        if not self.nogos:
            gaps.append("nogos")
        return gaps
