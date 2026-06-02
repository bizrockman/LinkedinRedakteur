"""Synthetic Persona entity — represents target-audience feedback."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PersonaEvaluation(BaseModel):
    """Output of a synthetic persona evaluating a post."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0, le=10)
    feedback: str
    persona_name: str | None = None
