"""PromptTemplate — eine benannte, Jinja2-fähige Prompt-Vorlage."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PromptTemplate(BaseModel):
    """Roh-Template (z.B. Jinja2-Quelle) + Metadaten."""

    model_config = ConfigDict(frozen=True)

    name: str  # z.B. "eve_system" oder "persona"
    body: str  # Jinja2-Quelle
    version: str = "1"
    description: str = ""
    updated_at: datetime | None = None


class RenderedPrompt(BaseModel):
    """Ergebnis nach dem Rendering mit einem ClientProfile."""

    model_config = ConfigDict(frozen=True)

    template_name: str
    profile_id: str
    body: str
    variables: dict = Field(default_factory=dict)  # Debug: was wurde eingesetzt
