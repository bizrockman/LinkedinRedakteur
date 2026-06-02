"""Wizard UI Protocol — der Vertrag zwischen Wizard-Use-Cases und einem Adapter.

Implementierungen:
- RichCliWizardUI (apps/onboarding/cli.py)
- FastAPIWizardUI (später, falls wir Web-Frontend bauen)
- TestWizardUI (für Unit-Tests)

Alle Methoden sind async, damit Web-Adapter mit Sockets/SSE arbeiten kann
und sich CLI nicht ändert.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable


@runtime_checkable
class WizardUI(Protocol):
    """Minimal-Vertrag, den ein Onboarding-UI erfüllen muss."""

    # --- Step-Lifecycle ---
    async def begin_step(self, step_number: int, total_steps: int, title: str) -> None: ...
    async def end_step(self) -> None: ...

    # --- Informational ---
    async def info(self, text: str) -> None: ...
    async def warn(self, text: str) -> None: ...
    async def instruct(self, *, url: str | None = None, instructions: str) -> None:
        """Zeigt Anweisungen, optional mit einer URL, die der User öffnen soll."""
        ...

    def progress(self, message: str) -> AbstractAsyncContextManager[None]:
        """Async-Context-Manager: zeigt einen Spinner/Progress-Indikator,
        solange der mit `async with` umschlossene Block läuft.

        Beispiel:
            async with ui.progress("Eve denkt nach..."):
                response = await llm.complete(...)
        """
        ...

    # --- Input ---
    async def ask_text(self, prompt: str, *, default: str | None = None) -> str: ...
    async def ask_multiline(self, prompt: str) -> str:
        """Multi-line Input (z.B. paste eines Analytics-Blocks)."""
        ...

    async def ask_yes_no(self, prompt: str, *, default: bool = True) -> bool: ...

    async def ask_choice(
        self, prompt: str, options: list[tuple[str, str]], *, default: int | None = None
    ) -> str:
        """Zeigt eine Auswahl-Liste. options: list of (key, label). Returns selected key."""
        ...

    # --- Bestätigung von Listen mit Möglichkeit zum Editieren ---
    async def confirm_list(
        self,
        title: str,
        items: list[str],
        *,
        allow_edit: bool = True,
        allow_regenerate: bool = True,
    ) -> tuple[str, list[str]]:
        """Zeigt Liste, fragt was tun.

        Returns (action, possibly_edited_items):
            action ∈ {"accept", "regenerate", "edit"}
            possibly_edited_items: bei "edit" die neue Liste, sonst unverändert
        """
        ...
