"""Schritt 2: Claim (Headline) + About-Text einsammeln.

Im Scraper-Modus aus dem Snapshot vorausgefüllt, User kann anpassen.
Im Manual-Modus fragen wir Schritt für Schritt.
"""

from __future__ import annotations

from eve.core.entities import ClientInfo
from eve.use_cases.onboarding.state import WizardState
from eve.use_cases.onboarding.ui import WizardUI

PROFILE_URL = "https://www.linkedin.com/in/<dein-username>/"


class BasicInfoStep:
    def __init__(self, ui: WizardUI) -> None:
        self.ui = ui

    async def run(self, state: WizardState) -> WizardState:
        await self.ui.begin_step(2, 8, "LinkedIn Claim & Info-Text")

        scraped_headline = state.snapshot.headline if state.snapshot else ""
        scraped_about = state.snapshot.about if state.snapshot else ""
        scraped_name = state.snapshot.name if state.snapshot else ""

        if scraped_headline:
            await self.ui.info(
                f"Aus dem Snapshot habe ich diesen Claim:\n\n"
                f'    "{scraped_headline}"\n'
            )
            keep = await self.ui.ask_yes_no("Diesen Claim übernehmen?", default=True)
            headline = scraped_headline if keep else await self.ui.ask_multiline(
                "Bitte deinen LinkedIn-Claim (Headline-Text)"
            )
        else:
            await self.ui.instruct(
                url=PROFILE_URL.replace("<dein-username>", "..."),
                instructions=(
                    "Geh auf dein LinkedIn-Profil. Direkt unter deinem Namen "
                    "siehst du deinen Claim (Headline) — der Text, der dich "
                    "in 1-2 Sätzen beschreibt. Kopiere ihn komplett."
                ),
            )
            headline = await self.ui.ask_multiline("Bitte Claim einfügen")

        # About
        if scraped_about and len(scraped_about) > 50:
            await self.ui.info(
                f"Und folgenden About-Text (Info-Section, {len(scraped_about)} Zeichen):\n\n"
                f"---\n{scraped_about[:600]}{'...' if len(scraped_about) > 600 else ''}\n---"
            )
            keep = await self.ui.ask_yes_no("Diesen About-Text übernehmen?", default=True)
            about = scraped_about if keep else await self.ui.ask_multiline(
                "Bitte den vollständigen About-Text einfügen"
            )
        else:
            await self.ui.instruct(
                instructions=(
                    "Scrolle auf deinem Profil ein Stück nach unten zur "
                    "Sektion 'Info' (englisch: 'About'). Klicke ggf. auf "
                    "'…mehr anzeigen', sodass der vollständige Text sichtbar "
                    "ist. Markiere ihn komplett und kopiere ihn."
                ),
            )
            about = await self.ui.ask_multiline(
                "About-Text einfügen (mehrzeilig erlaubt, leere Zeile zum Beenden)"
            )

        # Claim ans Anfang der description hängen, damit Eve ihn als
        # "Selbstbeschreibung in einem Satz" prominent sieht.
        state.profile.profile_id = state.profile_id
        state.profile.client = ClientInfo(
            name=scraped_name,
            description=f"Claim: {headline.strip()}\n\n{about.strip()}",
            linkedin_url=state.linkedin_url or "",
            topics=[],  # kommen in Step 3
        )

        await self.ui.info("Basisinfos erfasst.")
        await self.ui.end_step()
        return state
