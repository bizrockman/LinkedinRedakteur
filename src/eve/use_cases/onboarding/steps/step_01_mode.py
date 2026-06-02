"""Schritt 1: Modus wählen + (optional) komplettes Scraping vorab.

Wenn der User Scraper wählt:
- Zeigt ToS-Warnung
- Fragt nach LinkedIn-URL
- Startet PlaywrightLinkedInFetcher (persistent_context)
- Speichert Snapshot im WizardState — folgende Steps nutzen ihn als Default
"""

from __future__ import annotations

import logging

from eve.adapters.linkedin.playwright_fetcher import PlaywrightLinkedInFetcher
from eve.use_cases.onboarding.state import WizardState
from eve.use_cases.onboarding.ui import WizardUI

log = logging.getLogger(__name__)


TOS_WARNING = (
    "Achtung: Das automatische Scrapen von LinkedIn verstösst gegen die "
    "LinkedIn-Nutzungsbedingungen. Im Extremfall kann LinkedIn deinen Account "
    "vorübergehend oder dauerhaft sperren. Bei self-service-Nutzung mit dem "
    "eigenen Account und niedrigem Volumen ist das Risiko gering — aber "
    "es ist nicht null."
)


class ChooseModeStep:
    def __init__(self, ui: WizardUI) -> None:
        self.ui = ui

    async def run(self, state: WizardState) -> WizardState:
        await self.ui.begin_step(1, 8, "Modus & (optional) LinkedIn-Daten holen")

        await self.ui.info(
            "Zwei Wege, dein LinkedIn-Profil zu erfassen:\n\n"
            "  1) Automatisch via Browser-Scraper (Playwright)\n"
            "     → schnell, aber: siehe ToS-Warnung\n\n"
            "  2) Schritt für Schritt mit Copy-Paste\n"
            "     → manuell, dafür ohne ToS-Risiko und ohne Browser-Login"
        )

        mode = await self.ui.ask_choice(
            "Wie möchtest du vorgehen?",
            options=[
                ("scraper", "Automatisch via Browser-Scraper (mit ToS-Warnung)"),
                ("manual", "Schritt für Schritt mit Copy-Paste"),
            ],
            default=1,
        )
        state.use_scraper = mode == "scraper"

        if not state.use_scraper:
            await self.ui.info(
                "Gut. Wir gehen die Schritte gemeinsam durch — ich sage dir "
                "an jeder Stelle genau, was du wo kopieren musst."
            )
            await self.ui.end_step()
            return state

        # Scraper-Pfad
        await self.ui.warn(TOS_WARNING)
        proceed = await self.ui.ask_yes_no("Trotzdem mit Scraper fortfahren?", default=False)
        if not proceed:
            await self.ui.info("OK — wir wechseln zum manuellen Pfad.")
            state.use_scraper = False
            await self.ui.end_step()
            return state

        state.linkedin_url = await self.ui.ask_text(
            "Deine LinkedIn-Profil-URL "
            "(z.B. https://www.linkedin.com/in/dein-username/)"
        )

        await self.ui.info(
            "Starte den Browser. Beim ersten Lauf öffnet sich ein Chromium-"
            "Fenster — bitte logge dich dort manuell bei LinkedIn ein. "
            "Bei weiteren Läufen bleibt der Login erhalten."
        )

        fetcher = PlaywrightLinkedInFetcher(
            user_data_dir=".playwright_linkedin_profile",
            headless=False,
            login_timeout=300,
            posts_source="top",  # Top-Performer aus Creator-Analytics statt chronologisch
        )
        snapshot = await fetcher.fetch(state.linkedin_url, max_posts=20)
        state.snapshot = snapshot

        audience_info = (
            f"  Audience: {len(snapshot.audience.categories)} Demographics-Kategorien"
            if snapshot.audience
            else "  Audience: nicht gescrapt"
        )
        await self.ui.info(
            f"Snapshot erfasst:\n"
            f"  Name:    {snapshot.name or '(leer)'}\n"
            f"  Headline:{(snapshot.headline or '')[:80]}\n"
            f"  About:   {len(snapshot.about)} Zeichen\n"
            f"  Posts:   {len(snapshot.posts)} (Top-Performer)\n"
            f"{audience_info}"
        )

        await self.ui.end_step()
        return state
