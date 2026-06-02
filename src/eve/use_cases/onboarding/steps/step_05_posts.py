"""Schritt 5: Erfolgreichste Posts einsammeln + Posts-Sidecar speichern.

Im Scraper-Modus: User picked aus den gescrapten Posts die Top-5 als
Stil-Anker, ALLE gescrapten Posts wandern in die JSON-Sidecar.

Im Manual-Modus: User paste'd Post-Texte einzeln (1-5 Stück).
"""

from __future__ import annotations

import logging
from datetime import datetime

from eve.core.entities import (
    PostSource,
    PostStatus,
    StoredPost,
    SuccessfulPost,
)
from eve.core.ports import PromptRepository
from eve.use_cases.onboarding.state import WizardState
from eve.use_cases.onboarding.ui import WizardUI

log = logging.getLogger(__name__)

TOP_POSTS_URL = (
    "https://www.linkedin.com/analytics/creator/top-posts/"
    "?metricType=ENGAGEMENTS&timeRange=past_365_days"
)

PREVIEW_CHARS = 200


class TopPostsStep:
    def __init__(self, ui: WizardUI, prompts: PromptRepository) -> None:
        self.ui = ui
        self.prompts = prompts

    async def run(self, state: WizardState) -> WizardState:
        await self.ui.begin_step(5, 8, "Erfolgreichste Posts (Stil-Anker)")

        if state.snapshot and state.snapshot.posts:
            await self._scraper_path(state)
        else:
            await self._manual_path(state)

        # Persistieren via PromptRepository
        if state.stored_posts:
            await self.prompts.save_posts(
                state.stored_posts,
                profile_id=state.profile_id,
            )
            await self.ui.info(
                f"{len(state.stored_posts)} Posts in der JSON-Sidecar gespeichert."
            )

        await self.ui.end_step()
        return state

    # ------------------------------------------------------------------
    async def _scraper_path(self, state: WizardState) -> None:
        assert state.snapshot is not None
        await self.ui.info(
            f"Aus dem Creator-Analytics-Dashboard habe ich {len(state.snapshot.posts)} "
            "Top-Performer-Posts (nach Engagement sortiert, beste zuerst). "
            "Alle wandern als Historie in die JSON-Sidecar. "
            "Welche willst du als Stil-Anker im Profil hervorheben?"
        )

        # Übersicht
        previews = [
            f"{i + 1}. {(p.text[:PREVIEW_CHARS] or '').replace(chr(10), ' ')}"
            f"{'…' if len(p.text) > PREVIEW_CHARS else ''}"
            for i, p in enumerate(state.snapshot.posts)
        ]
        for line in previews:
            await self.ui.info(line)

        chosen_str = await self.ui.ask_text(
            "Nummern deiner Top-Posts (komma-getrennt, z.B. '1,3,5')",
            default="1,2,3",
        )
        chosen_indices = _parse_indices(chosen_str, max_index=len(state.snapshot.posts))

        # Stil-Anker fürs ClientProfile
        state.profile.successful_posts = [
            SuccessfulPost(text=state.snapshot.posts[i].text)
            for i in chosen_indices
        ]

        # Alle Posts als StoredPost (linkedin_import)
        now = datetime.now()
        state.stored_posts = [
            StoredPost(
                text=p.text,
                source=PostSource.LINKEDIN_IMPORT,
                status=PostStatus.POSTED,
                posted_at=p.posted_at,
                linkedin_url=p.url,
                imported_at=now,
            )
            for p in state.snapshot.posts
        ]

    async def _manual_path(self, state: WizardState) -> None:
        await self.ui.instruct(
            url=TOP_POSTS_URL,
            instructions=(
                "Öffne dein Creator-Dashboard → Top-Beiträge (sortiert nach "
                "Engagement). Für jeden der Top-Posts:\n"
                "  • Öffne ihn\n"
                "  • Kopiere den **Text** (Markiere die Inhaltsbeschreibung)\n"
                "  • Füge ihn unten ein\n"
                "Bei leerer Eingabe schliessen wir den Schritt ab. "
                "Empfohlen: 3-5 Posts. Bei null Posts ist das auch OK "
                "(z.B. wenn das Profil neu ist)."
            ),
        )

        now = datetime.now()
        successful: list[SuccessfulPost] = []
        stored: list[StoredPost] = []
        for i in range(1, 6):
            text = await self.ui.ask_multiline(
                f"Post {i} (komplett mit Leerzeilen, leer = Ende)"
            )
            if not text.strip():
                break
            successful.append(SuccessfulPost(text=text.strip()))
            stored.append(
                StoredPost(
                    text=text.strip(),
                    source=PostSource.MANUAL_IMPORT,
                    status=PostStatus.POSTED,
                    imported_at=now,
                )
            )

        state.profile.successful_posts = successful
        state.stored_posts = stored


def _parse_indices(s: str, *, max_index: int) -> list[int]:
    """Parst '1,3,5' → [0, 2, 4] (0-indexed), filtert ungültige."""
    result: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            idx = int(part) - 1
            if 0 <= idx < max_index:
                result.append(idx)
        except ValueError:
            continue
    return result
