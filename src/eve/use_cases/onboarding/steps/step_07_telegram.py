"""Schritt 7: Telegram-Bot Setup (Mock).

Aktuell Platzhalter — zeigt dem User den geplanten Setup-Flow für den
Telegram-Bot. Volle Implementierung folgt mit dem TelegramMessenger-Adapter.
"""

from __future__ import annotations

import logging

from eve.use_cases.onboarding.state import WizardState
from eve.use_cases.onboarding.ui import WizardUI

log = logging.getLogger(__name__)

BOTFATHER_URL = "https://t.me/BotFather"
USERINFOBOT_URL = "https://t.me/userinfobot"


class TelegramMockStep:
    def __init__(self, ui: WizardUI) -> None:
        self.ui = ui

    async def run(self, state: WizardState) -> WizardState:
        await self.ui.begin_step(7, 8, "Telegram-Bot (Vorschau)")

        await self.ui.info(
            "Mit einem Telegram-Bot sprichst du Eve auch von unterwegs an —\n"
            "Text, Sprachnachrichten (→ Whisper), Bilder (→ Vision), PDFs.\n"
            "Antworten kommen direkt in deinem Chat.\n"
        )

        await self.ui.warn(
            "Vorschau-Schritt — die echte Bot-Integration folgt in einer der "
            "nächsten Releases. Heute kannst du die Daten schon vorbereiten, "
            "sie sind dann später sofort einsatzbereit."
        )

        proceed = await self.ui.ask_yes_no(
            "Möchtest du den Bot jetzt schon anlegen und den Token vormerken?",
            default=False,
        )
        if not proceed:
            await self.ui.info(
                "OK, überspringen. Du kannst Telegram später jederzeit nachrüsten."
            )
            await self.ui.end_step()
            return state

        # --- Schritt-Anleitung
        await self.ui.instruct(
            url=BOTFATHER_URL,
            instructions=(
                "1. Telegram öffnen, suche [bold]@BotFather[/bold]\n"
                "2. Schicke ihm [cyan]/newbot[/cyan]\n"
                "3. Gib einen [bold]Anzeigename[/bold] für den Bot ein\n"
                "   (z.B. 'Eve - LinkedIn-Redakteur')\n"
                "4. Wähle einen [bold]Username[/bold] (muss auf 'bot' enden,\n"
                "   z.B. 'eve_redakteur_bot')\n"
                "5. BotFather schickt dir einen Token in folgendem Format:\n"
                "   [dim]123456789:AAExxxxxxxxxxxxxxxxxxxxxxxx[/dim]"
            ),
        )
        bot_token = await self.ui.ask_text(
            "Bot-Token (oder leer lassen zum Überspringen)", default=""
        )

        if bot_token.strip():
            await self.ui.instruct(
                url=USERINFOBOT_URL,
                instructions=(
                    "Damit der Bot nur auf dich hört, brauchen wir deine User-ID:\n"
                    "1. Schreib in Telegram [bold]@userinfobot[/bold]\n"
                    "2. Er antwortet mit deiner numerischen ID\n"
                    "3. ID hier einfügen:"
                ),
            )
            user_id = await self.ui.ask_text(
                "Deine Telegram User-ID (oder leer)", default=""
            )

            # Mock-Speicherung im WizardState — wird beim späteren Real-Adapter konsumiert
            state.telegram_mock = {
                "bot_token": bot_token.strip(),
                "user_id": user_id.strip(),
            }
            await self.ui.info(
                "✓ Token + User-ID gespeichert (Mock).\n"
                "  → Bei der echten Integration wandern sie in [cyan]eve_tokens[/cyan]\n"
                "  → Du wirst dann via [cyan]eve auth telegram[/cyan] zur Aktivierung\n"
                "    aufgefordert."
            )
        else:
            await self.ui.info("OK, kein Token eingegeben — übersprungen.")

        await self.ui.end_step()
        return state
