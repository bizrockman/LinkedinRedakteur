"""evaluate_with_persona-Tool — sub-agent für Post-Reviews.

Pattern: internally macht das Tool einen LLM-Call mit dem Persona-System-Prompt
(die Persona "spielt" sich selbst) und liefert deren Feedback + Score zurück.

n8n hatte das mit `Synthetic Persona` als langchain-Tool — wir machen es im
Code: rendert persona.md.j2 für die ausgewählte Persona, schickt sie als
System-Prompt + den zu bewertenden Post-Text als User-Message.
"""

from __future__ import annotations

import logging
from typing import Any

from eve.agent.tools.base import ToolDefinition
from eve.core.entities import LLMMessage
from eve.core.ports import LLMProvider, PromptRepository

log = logging.getLogger(__name__)


class EvaluateWithPersonaTool:
    def __init__(
        self,
        prompts: PromptRepository,
        llm: LLMProvider,
        profile_id: str,
        *,
        model: str = "claude-opus-4-7",
    ) -> None:
        self.prompts = prompts
        self.llm = llm
        self.profile_id = profile_id
        self.model = model

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="evaluate_with_persona",
            description=(
                "Lass eine Kunden-Avatar-Persona Feedback zu einem Post-Entwurf geben. "
                "Die Persona antwortet aus ihrer eigenen Perspektive (1. Person Singular) "
                "und gibt einen Score 0-10. Nutze dies BEVOR du dem User einen Post "
                "präsentierst — und iteriere bis du mindestens 7/10 erreichst."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "post_text": {
                        "type": "string",
                        "description": "Der zu bewertende Post-Entwurf",
                    },
                    "persona_name": {
                        "type": "string",
                        "description": (
                            "Optional: Name der gewünschten Persona. Wenn nicht angegeben "
                            "wird die erste Persona des Profils verwendet."
                        ),
                    },
                },
                "required": ["post_text"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> str:
        post_text = args.get("post_text", "").strip()
        if not post_text:
            return "Fehler: post_text ist leer."

        profile = await self.prompts.get_profile(self.profile_id)
        if not profile.personas:
            return "Fehler: keine Personas im Profil definiert."

        wanted_name = args.get("persona_name")
        persona = None
        if wanted_name:
            persona = next(
                (p for p in profile.personas if p.name.lower() == wanted_name.lower()),
                None,
            )
            if persona is None:
                names = [p.name for p in profile.personas]
                return f"Persona '{wanted_name}' nicht gefunden. Verfügbar: {names}"
        if persona is None:
            persona = profile.personas[0]

        # Persona-System-Prompt rendern
        rendered = await self.prompts.render(
            "persona",
            profile_id=self.profile_id,
            extra_context={"persona": persona},
        )

        log.info("Evaluating post via persona '%s'", persona.name)
        response = await self.llm.complete(
            messages=[
                LLMMessage(
                    role="user",
                    content=f"Hier mein aktueller Post-Entwurf für LinkedIn:\n\n---\n{post_text}\n---\n\nBitte gib mir dein ehrliches Feedback inkl. Score.",
                )
            ],
            model=self.model,
            system=rendered.body,
            max_tokens=1500,
        )

        return f"--- Feedback von Persona '{persona.name}' ---\n\n{response.content}"
