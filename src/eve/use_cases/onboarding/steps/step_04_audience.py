"""Schritt 4: Zielgruppen-Beschreibung aus LinkedIn-Analytics ableiten."""

from __future__ import annotations

import logging
import re

from eve.core.entities import LLMMessage, TargetAudience
from eve.core.ports import LLMProvider, PromptRepository
from eve.use_cases.onboarding.state import WizardState
from eve.use_cases.onboarding.ui import WizardUI

log = logging.getLogger(__name__)

AUDIENCE_URL = (
    "https://www.linkedin.com/analytics/demographic-detail/"
    "urn:li:fsd_profile:profile/?metricType=MEMBER_FOLLOWERS"
)


class AudienceStep:
    def __init__(
        self,
        ui: WizardUI,
        llm: LLMProvider,
        prompts: PromptRepository,
        *,
        model: str = "claude-opus-4-7",
    ) -> None:
        self.ui = ui
        self.llm = llm
        self.prompts = prompts
        self.model = model

    async def run(self, state: WizardState) -> WizardState:
        await self.ui.begin_step(4, 6, "Zielgruppe (Analytics-basiert)")

        # 1) Scraper-Pfad: snapshot.audience wurde bereits in Step 1 mitgescrapt
        if state.snapshot and state.snapshot.audience:
            analytics = state.snapshot.audience.to_paste_block()
            await self.ui.info(
                f"Demographics aus dem Scraper geladen: "
                f"{len(state.snapshot.audience.categories)} Kategorien "
                f"({', '.join(state.snapshot.audience.categories.keys())})."
            )
        else:
            # 2) Manual-Pfad: User pastet
            await self.ui.instruct(
                url=AUDIENCE_URL,
                instructions=(
                    "Öffne die URL (LinkedIn Creator-Dashboard, Demographics).\n"
                    "Kopiere die Block-Listen für **Jobbezeichnung**, **Standort**, "
                    "**Branche**, **Karrierestufe** und **Firmengröße** "
                    "(jeweils mit den Prozentzahlen).\n"
                    "**Nicht** die Unternehmensnamen — die brauchen wir nicht.\n\n"
                    "Füge alles zusammen in einem Block ein."
                ),
            )
            analytics = await self.ui.ask_multiline(
                "LinkedIn-Analytics einfügen (leere Zeile zum Beenden)"
            )

        if not analytics.strip():
            await self.ui.warn(
                "Keine Analytics-Daten verfügbar — Audience-Block bleibt leer. "
                "Du kannst ihn später manuell im YAML ergänzen."
            )
            await self.ui.end_step()
            return state

        rendered = await self.prompts.render_raw(
            "wizard_derive_audience",
            context={"analytics_paste": analytics.strip()},
        )
        async with self.ui.progress("Eve analysiert die Zielgruppen-Daten ..."):
            response = await self.llm.complete(
                messages=[LLMMessage(role="user", content=rendered.body)],
                model=self.model,
                max_tokens=800,
            )

        description = _strip_lead_in(response.content)
        organization = _extract_dominant_industry(analytics)

        await self.ui.info(
            f"Abgeleiteter Zielgruppen-Block:\n\n---\n{description}\n---"
        )

        accept = await self.ui.ask_yes_no("Übernehmen?", default=True)
        if not accept:
            description = await self.ui.ask_multiline(
                "Eigene Zielgruppen-Beschreibung einfügen"
            )

        state.profile.audience = TargetAudience(
            description=description.strip(),
            organization=organization,
        )
        await self.ui.end_step()
        return state


def _strip_lead_in(text: str) -> str:
    """Entfernt 'The target audience you write for:' Vorspann falls vorhanden."""
    cleaned = re.sub(
        r"^The target audience you write for:\s*\n+",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _extract_dominant_industry(analytics: str) -> str:
    """Versucht die Top-Branche aus dem Analytics-Paste zu extrahieren."""
    # Suche "Branche\n<Top-Eintrag>"
    match = re.search(r"Branche\s*\n\s*([^\n]+)", analytics)
    if match:
        return match.group(1).strip()
    return ""
