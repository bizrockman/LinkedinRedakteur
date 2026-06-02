"""PromptRepository port — DAO für Prompt-Templates und Client-Profile.

Heute: Filesystem (prompts/templates/*.md.j2, prompts/profiles/*.yaml).
Morgen: Supabase oder beliebige andere Quelle — Port bleibt identisch.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from eve.core.entities import ClientProfile, PromptTemplate, RenderedPrompt, StoredPost


@runtime_checkable
class PromptRepository(Protocol):
    """Storage und Rendering von Prompts + Kundenprofilen."""

    # --- Templates -------------------------------------------------------
    async def get_template(self, name: str) -> PromptTemplate:
        """Lädt ein benanntes Template. Wirft KeyError, wenn nicht vorhanden."""
        ...

    async def list_templates(self) -> list[str]: ...

    # --- Profiles --------------------------------------------------------
    async def get_profile(self, profile_id: str | None = None) -> ClientProfile:
        """Lädt ein Kundenprofil. Wenn `profile_id` None ist, wird das Default geladen.

        Wirft KeyError, wenn das Profil nicht existiert oder kein Default gesetzt ist.
        """
        ...

    async def save_profile(self, profile: ClientProfile) -> ClientProfile:
        """Speichert ein Profil (Onboarding / Update). Setzt updated_at.

        Wenn noch kein Default-Profil existiert, wird dieses Profil zum Default.
        """
        ...

    async def delete_profile(self, profile_id: str) -> None:
        """Löscht ein Profil. Wenn es das Default war, wird der Default-Pointer entfernt."""
        ...

    async def list_profiles(self) -> list[str]: ...

    # --- Posts (sidecar, später: Supabase) -------------------------------
    async def load_posts(self, profile_id: str | None = None) -> list[StoredPost]:
        """Lädt alle gespeicherten Posts eines Profils (Editorial + Historie)."""
        ...

    async def save_posts(
        self, posts: list[StoredPost], *, profile_id: str | None = None
    ) -> None:
        """Speichert/überschreibt die komplette Posts-Liste eines Profils."""
        ...

    async def get_default_profile_id(self) -> str | None:
        """Aktuell als Default markiertes Profil oder None."""
        ...

    async def set_default_profile_id(self, profile_id: str) -> None:
        """Markiert ein Profil als Default. Profil muss existieren."""
        ...

    # --- Rendering -------------------------------------------------------
    async def render(
        self,
        template_name: str,
        *,
        profile_id: str | None = None,
        extra_context: dict | None = None,
    ) -> RenderedPrompt:
        """Bequemer Combo: Template + Profile → fertiger Prompt-String.

        Wenn `profile_id` None ist, wird das Default-Profil verwendet.
        """
        ...

    async def render_raw(
        self,
        template_name: str,
        *,
        context: dict | None = None,
    ) -> RenderedPrompt:
        """Rendert ein Template ohne Profil-Lookup — z.B. für Wizard-Templates,
        die ihren gesamten Context selbst mitbringen.
        """
        ...
