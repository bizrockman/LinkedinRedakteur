"""Schritt 8: LinkedIn-Authorization (Mock).

Aktuell Platzhalter — zeigt dem User den geplanten OAuth-Flow.
Volle Implementierung folgt mit dem LinkedInPublisher-Adapter.
"""

from __future__ import annotations

import logging

from eve.use_cases.onboarding.state import WizardState
from eve.use_cases.onboarding.ui import WizardUI

log = logging.getLogger(__name__)

LINKEDIN_DEV_URL = "https://developer.linkedin.com/apps"


class LinkedInMockStep:
    def __init__(self, ui: WizardUI) -> None:
        self.ui = ui

    async def run(self, state: WizardState) -> WizardState:
        await self.ui.begin_step(8, 8, "LinkedIn-Authorization (Vorschau)")

        await self.ui.info(
            "Damit Eve in deinem Namen Posts veröffentlichen kann, brauchst du\n"
            "eine LinkedIn-Developer-App mit OAuth-Flow.\n"
        )

        await self.ui.warn(
            "Vorschau-Schritt — der echte OAuth-Browser-Flow folgt mit dem\n"
            "LinkedInPublisher-Adapter. Heute zeigen wir dir nur das Setup."
        )

        proceed = await self.ui.ask_yes_no(
            "Möchtest du die LinkedIn-Developer-App jetzt schon einrichten?",
            default=False,
        )
        if not proceed:
            await self.ui.info(
                "OK, überspringen. Eve schreibt deine Posts trotzdem in den\n"
                "Editorial Plan — sie werden später, sobald die OAuth aktiv ist,\n"
                "automatisch zum geplanten Datum gepostet."
            )
            await self.ui.end_step()
            return state

        await self.ui.instruct(
            url=LINKEDIN_DEV_URL,
            instructions=(
                "1. Geh auf [bold]developer.linkedin.com/apps[/bold]\n"
                "2. [bold]Create App[/bold]:\n"
                "   • App name: 'Eve LinkedIn Redakteur'\n"
                "   • LinkedIn Page: deine Unternehmensseite (oder Personal)\n"
                "   • App logo: irgendein Bild\n"
                "3. Tab [bold]Products[/bold] → request:\n"
                "   • 'Share on LinkedIn' (für w_member_social Scope)\n"
                "   • 'Sign In with LinkedIn using OpenID Connect' (für r_basicprofile)\n"
                "4. Tab [bold]Auth[/bold] → 'OAuth 2.0 settings':\n"
                "   • Authorized redirect URLs: [cyan]http://localhost:8765/callback[/cyan]\n"
                "5. Tab [bold]Auth[/bold] → [bold]Client ID[/bold] und [bold]Client Secret[/bold] kopieren"
            ),
        )

        client_id = await self.ui.ask_text(
            "LinkedIn Client ID (oder leer zum Überspringen)", default=""
        )
        if not client_id.strip():
            await self.ui.info("OK, übersprungen.")
            await self.ui.end_step()
            return state

        client_secret = await self.ui.ask_text("Client Secret", default="")

        await self.ui.info(
            "In der späteren echten Variante würde jetzt ein Browser-Fenster zu LinkedIn\n"
            "öffnen. Du würdest dich einloggen + 'Allow' klicken. Eve fängt den Callback\n"
            "ab und tauscht den Code gegen Access + Refresh Tokens — die landen\n"
            "verschlüsselt (Fernet) in [cyan]eve_tokens[/cyan]."
        )

        # Mock-Speicherung im WizardState — wird beim späteren Real-Adapter konsumiert
        state.linkedin_mock = {
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
        }

        await self.ui.info(
            "✓ Client-ID + Secret gespeichert (Mock).\n"
            "  → Bei aktivem Adapter: [cyan]eve auth linkedin[/cyan] startet den OAuth-Flow."
        )

        await self.ui.end_step()
        return state
