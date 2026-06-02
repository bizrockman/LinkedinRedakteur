"""Schritt 3: Topics-Cluster mit LLM-Vorschlägen + Personal-Notes.

LLM generiert 6 Themen aus Claim + About + (optional) ersten Posts.
User kann akzeptieren, regenerieren, einzelne editieren oder Personal-Topics
hinzufügen ("Salz in der Suppe").
"""

from __future__ import annotations

import logging
import re

from eve.core.entities import LLMMessage
from eve.core.ports import LLMProvider, PromptRepository
from eve.use_cases.onboarding.state import WizardState
from eve.use_cases.onboarding.ui import WizardUI

log = logging.getLogger(__name__)


class TopicsStep:
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
        await self.ui.begin_step(3, 6, "Themen / Topics")

        topics = await self._generate(state)

        while True:
            action, edited = await self.ui.confirm_list(
                "Vorgeschlagene Themen",
                topics,
                allow_edit=True,
                allow_regenerate=True,
            )
            if action == "regenerate":
                topics = await self._generate(state)
                continue
            if action == "edit":
                topics = edited
                continue
            if action == "accept":
                topics = edited
                break

        # Personal-Topics ("Salz in der Suppe")
        await self.ui.info(
            "Jetzt 1-2 persönliche Themen, die deinen Content einzigartig machen — "
            "das, was den Unterschied macht. (Leer lassen = überspringen)"
        )
        for i in range(1, 3):
            p = await self.ui.ask_text(f"Persönliches Thema {i} (leer = Ende)", default="")
            if not p.strip():
                break
            topics.append(p.strip())

        state.profile.client = state.profile.client.model_copy(update={"topics": topics})
        await self.ui.info(f"Themen final ({len(topics)}):")
        for t in topics:
            await self.ui.info(f"  • {t}")

        await self.ui.end_step()
        return state

    # ------------------------------------------------------------------
    async def _generate(self, state: WizardState) -> list[str]:
        """LLM-Call: 6 Topics aus Claim + About + Posts."""
        rendered = await self.prompts.render_raw(
            "wizard_suggest_topics",
            context={
                "headline": self._extract_headline(state.profile.client.description),
                "about": self._extract_about(state.profile.client.description),
                "existing_posts": state.snapshot.posts if state.snapshot else [],
            },
        )
        # Wir nutzen das gerenderte Template als USER-Message, nicht system.
        async with self.ui.progress("Eve generiert 6 Themen-Vorschläge ..."):
            response = await self.llm.complete(
                messages=[LLMMessage(role="user", content=rendered.body)],
                model=self.model,
                max_tokens=1024,
            )
        topics = _parse_bullet_list(response.content)
        log.info("LLM suggested %d topics", len(topics))
        return topics

    @staticmethod
    def _extract_headline(description: str) -> str:
        # Description hat Format "Claim: ...\n\n<about>"
        match = re.match(r"^Claim:\s*(.+?)\n\n", description, re.DOTALL)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_about(description: str) -> str:
        parts = description.split("\n\n", 1)
        return parts[1].strip() if len(parts) > 1 else description


def _parse_bullet_list(text: str) -> list[str]:
    """Parst eine Markdown-Liste, robust gegen Variationen."""
    lines = text.strip().splitlines()
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        # `- foo`, `* foo`, `1. foo`
        m = re.match(r"^(?:[-*]|\d+[.)])\s+(.+)$", stripped)
        if m:
            items.append(m.group(1).strip().strip("*_"))
    return items
