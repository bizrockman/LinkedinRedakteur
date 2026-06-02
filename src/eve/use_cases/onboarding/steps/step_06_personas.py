"""Schritt 6: Buyer-Personas (Kunden-Avatare) via LLM generieren.

Anders als die synthetische Test-Persona (Default-"Nora") sind das echte
Kunden-Avatare — zwei distinct Profile, die Eve später nutzt um Posts aus
Kundenperspektive zu evaluieren ("Würde mich dieser Post als 45-jähriger
CEO eines IT-Beratungshauses überhaupt ansprechen?").

LLM-Output wird in zwei `SyntheticPersona`-Entitäten geparst.
"""

from __future__ import annotations

import logging
import re

from eve.core.entities import LLMMessage, SyntheticPersona
from eve.core.ports import LLMProvider, PromptRepository
from eve.use_cases.onboarding.state import WizardState
from eve.use_cases.onboarding.ui import WizardUI

log = logging.getLogger(__name__)

DEFAULT_NAMES = ["Markus", "Lena"]  # Fallback wenn LLM keinen Namen liefert


class PersonasStep:
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
        await self.ui.begin_step(6, 8, "Kunden-Avatare (Buyer Personas)")

        if not state.profile.audience.description:
            await self.ui.warn(
                "Keine Audience-Beschreibung vorhanden — überspringe Avatar-Generierung. "
                "Du kannst sie später manuell im YAML eintragen."
            )
            await self.ui.end_step()
            return state

        await self.ui.info(
            "Eve leitet aus deiner Audience + Themen zwei Kunden-Avatare ab. "
            "Diese nutzt sie später, um Posts vor Veröffentlichung aus deren "
            "Perspektive zu bewerten."
        )

        personas = await self._generate(state)

        while True:
            preview = [self._format_for_review(p) for p in personas]
            action, _ = await self.ui.confirm_list(
                "Generierte Avatare",
                preview,
                allow_edit=False,
                allow_regenerate=True,
            )
            if action == "regenerate":
                personas = await self._generate(state)
                continue
            break

        state.profile.personas = personas
        await self.ui.info(
            f"✓ {len(personas)} Avatare gespeichert: "
            + ", ".join(p.name for p in personas)
        )
        await self.ui.end_step()
        return state

    # ------------------------------------------------------------------
    async def _generate(self, state: WizardState) -> list[SyntheticPersona]:
        analytics_raw = ""
        if state.snapshot and state.snapshot.audience:
            analytics_raw = state.snapshot.audience.to_paste_block()

        rendered = await self.prompts.render_raw(
            "wizard_generate_personas",
            context={
                "audience_description": state.profile.audience.description,
                "analytics_raw": analytics_raw or "(nicht verfügbar)",
                "topics": state.profile.client.topics,
                "client_description": state.profile.client.description,
            },
        )
        async with self.ui.progress("Eve generiert zwei Kunden-Avatare ..."):
            response = await self.llm.complete(
                messages=[LLMMessage(role="user", content=rendered.body)],
                model=self.model,
                max_tokens=2000,
            )

        personas = _parse_personas(response.content)
        if not personas:
            log.warning("Persona-Parser fand nichts; LLM-Output:\n%s", response.content[:500])
            await self.ui.warn(
                "Konnte die LLM-Antwort nicht in Personas parsen. "
                "Bitte regenerieren oder später manuell im YAML eintragen."
            )
            return []
        log.info("Parsed %d personas from LLM output", len(personas))
        return personas

    @staticmethod
    def _format_for_review(persona: SyntheticPersona) -> str:
        # Bullets sind in der Liste schon nummeriert — gib alles als Block-Text aus
        return (
            f"[{persona.name}]\n"
            f"Role: {persona.role[:300]}{'…' if len(persona.role) > 300 else ''}\n"
            f"Organization: {persona.organization[:200]}"
            f"{'…' if len(persona.organization) > 200 else ''}"
        )


# ----------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------
_PERSONA_BLOCK_RE = re.compile(
    r"PERSONA\s+(\d+)\s*\n+(.*?)(?=\nPERSONA\s+\d+|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_ROLE_RE = re.compile(r"<Role>\s*(.*?)\s*</Role>", re.IGNORECASE | re.DOTALL)
_ORG_RE = re.compile(r"<Organization>\s*(.*?)\s*</Organization>", re.IGNORECASE | re.DOTALL)


def _parse_personas(text: str) -> list[SyntheticPersona]:
    """Zwei PERSONA-Blöcke aus LLM-Output extrahieren.

    Erwartetes Format (siehe wizard_generate_personas.md.j2):
        PERSONA 1
        <Role>...</Role>
        <Organization>...</Organization>

        PERSONA 2
        <Role>...</Role>
        <Organization>...</Organization>
    """
    out: list[SyntheticPersona] = []
    for match in _PERSONA_BLOCK_RE.finditer(text):
        idx = int(match.group(1))
        body = match.group(2)
        role_match = _ROLE_RE.search(body)
        org_match = _ORG_RE.search(body)
        if not role_match:
            continue
        role = role_match.group(1).strip()
        organization = org_match.group(1).strip() if org_match else ""
        out.append(
            SyntheticPersona(
                name=_extract_name(role) or DEFAULT_NAMES[(idx - 1) % len(DEFAULT_NAMES)],
                role=role,
                organization=organization,
            )
        )
    return out


def _extract_name(role_text: str) -> str | None:
    """Versucht, einen Vornamen aus dem Role-Text zu extrahieren.

    Unterstützte Formate:
        "Markus, ein 45-jähriger CFO ..."     → Markus
        "Markus ist ein 45-jähriger ..."       → Markus
        "Act as Markus, a 45-year-old ..."     → Markus (Legacy-Format)
    """
    stripped = role_text.lstrip()
    # Legacy: "Act as Vorname[, ...]"
    match = re.match(r"Act as\s+([A-ZÄÖÜ][a-zäöüß]+)\b", stripped)
    if match:
        candidate = match.group(1)
        if candidate.lower() not in _NON_NAME_WORDS:
            return candidate

    # Neues Format: "Vorname, ..." oder "Vorname ist ..."
    match = re.match(r"([A-ZÄÖÜ][a-zäöüß]+)(?:\s*,|\s+ist\s+)", stripped)
    if match:
        candidate = match.group(1)
        if candidate.lower() not in _NON_NAME_WORDS:
            return candidate
    return None


# Wörter, die zwar großgeschrieben am Satzanfang stehen können, aber keine
# Namen sind — Fallback-Schutz, damit "Eine 45-jährige …" nicht "Eine" als
# Namen identifiziert.
_NON_NAME_WORDS = {
    # Englisch
    "a", "an", "the",
    # Deutsch Artikel/Indefinite/Demonstrative
    "der", "die", "das", "den", "dem", "des",
    "ein", "eine", "einer", "einem", "einen", "eines",
    "dieser", "diese", "dieses",
    # Häufige Satzeröffnungen aus dem neuen Format
    "du", "sie", "er", "als",
}
