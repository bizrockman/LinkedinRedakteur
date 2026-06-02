"""LinkedInProfileFetcher port — Quelle für Profil + Posts.

Implementierungen:
- PlaywrightLinkedInFetcher (headful, mit Cookie-Persistenz)
- ProxycurlLinkedInFetcher (paid API, später)
- GdprExportLinkedInFetcher (CSV-Upload, später)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from eve.core.entities import LinkedInProfileSnapshot


@runtime_checkable
class LinkedInProfileFetcher(Protocol):
    @property
    def source_name(self) -> str:
        """Z.B. 'playwright', 'proxycurl', 'gdpr-export'."""
        ...

    async def fetch(
        self,
        profile_url: str,
        *,
        max_posts: int = 25,
    ) -> LinkedInProfileSnapshot:
        """Lädt das Profil + die letzten N Posts.

        Args:
            profile_url: Voll qualifizierte URL (z.B. https://www.linkedin.com/in/username/)
            max_posts: Soft-Limit für die Anzahl gescrapter Posts.
        """
        ...
