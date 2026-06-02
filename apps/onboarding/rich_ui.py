"""RichCliWizardUI — terminal-basierter Adapter für das WizardUI Protocol.

Nutzt Rich für Panels, Prompts, Multi-line Input, Listen.

Multi-line Input: zwei aufeinanderfolgende leere Zeilen beenden die Eingabe.
Funktioniert in Windows Terminal, PowerShell 7+, und allen Unix-Shells.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table


class RichCliWizardUI:
    """Implementiert WizardUI Protocol via Rich Console."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    # ------------------------------------------------------------------
    # Step lifecycle
    # ------------------------------------------------------------------
    async def begin_step(self, step_number: int, total_steps: int, title: str) -> None:
        self.console.print()
        self.console.print(Rule(f"[bold cyan]Schritt {step_number}/{total_steps}: {title}"))
        self.console.print()

    async def end_step(self) -> None:
        self.console.print()

    # ------------------------------------------------------------------
    # Informational
    # ------------------------------------------------------------------
    async def info(self, text: str) -> None:
        self.console.print(text)

    async def warn(self, text: str) -> None:
        self.console.print(Panel(text, title="[yellow]Achtung", border_style="yellow"))

    async def instruct(self, *, url: str | None = None, instructions: str) -> None:
        body = instructions
        if url:
            body = f"[bold]URL:[/bold] [link]{url}[/link]\n\n{instructions}"
        self.console.print(Panel(body, title="[bold]Anweisung", border_style="cyan"))

    @asynccontextmanager
    async def progress(self, message: str) -> AsyncIterator[None]:
        """Rich Spinner über den Console.status()-Mechanismus.

        Funktioniert in async, weil Rich seinen Spinner in einem Hintergrund-Thread
        rendert — der Event-Loop bleibt frei für den LLM-Call.
        """
        with self.console.status(f"[cyan]{message}", spinner="dots"):
            yield

    # ------------------------------------------------------------------
    # Single-line input
    # ------------------------------------------------------------------
    async def ask_text(self, prompt: str, *, default: str | None = None) -> str:
        return Prompt.ask(prompt, default=default or "", console=self.console)

    async def ask_multiline(self, prompt: str) -> str:
        """Multi-line: zwei aufeinanderfolgende leere Zeilen beenden."""
        self.console.print(
            f"[dim]{prompt}[/dim]\n"
            "[dim](2x Enter für Ende, oder Ctrl+D / Ctrl+Z+Enter unter Windows)[/dim]"
        )
        lines: list[str] = []
        empty_count = 0
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line == "":
                empty_count += 1
                if empty_count >= 2:
                    break
                lines.append(line)
                continue
            empty_count = 0
            lines.append(line)
        return "\n".join(lines).strip()

    async def ask_yes_no(self, prompt: str, *, default: bool = True) -> bool:
        return Confirm.ask(prompt, default=default, console=self.console)

    # ------------------------------------------------------------------
    # Choice & List
    # ------------------------------------------------------------------
    async def ask_choice(
        self,
        prompt: str,
        options: list[tuple[str, str]],
        *,
        default: int | None = None,
    ) -> str:
        table = Table(show_header=False, show_lines=False, box=None, padding=(0, 1))
        table.add_column(style="bold cyan", width=3)
        table.add_column()
        for i, (_key, label) in enumerate(options, 1):
            marker = "▶" if default is not None and i == default else " "
            table.add_row(f"{marker}{i}", label)
        self.console.print(table)

        choices = [str(i) for i in range(1, len(options) + 1)]
        default_choice = str(default) if default is not None else None
        selected = Prompt.ask(
            prompt, choices=choices, default=default_choice, console=self.console
        )
        return options[int(selected) - 1][0]

    async def confirm_list(
        self,
        title: str,
        items: list[str],
        *,
        allow_edit: bool = True,
        allow_regenerate: bool = True,
    ) -> tuple[str, list[str]]:
        while True:
            self._render_numbered_list(title, items)
            options = [("accept", "Akzeptieren")]
            if allow_regenerate:
                options.append(("regenerate", "Neu generieren"))
            if allow_edit:
                options.append(("edit", "Eintrag editieren"))
                options.append(("delete", "Eintrag löschen"))
            action = await self.ask_choice("Aktion?", options, default=1)

            if action in ("accept", "regenerate"):
                return action, items

            if action == "edit":
                idx_str = await self.ask_text(
                    f"Welcher Eintrag (1-{len(items)})?", default="1"
                )
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(items):
                        new_text = await self.ask_text(
                            f"Neuer Text für Eintrag {idx + 1}", default=items[idx]
                        )
                        items[idx] = new_text.strip() or items[idx]
                except ValueError:
                    self.console.print("[red]Ungültige Eingabe[/red]")
                continue

            if action == "delete":
                idx_str = await self.ask_text(
                    f"Welcher Eintrag (1-{len(items)})?", default=str(len(items))
                )
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(items):
                        del items[idx]
                except ValueError:
                    self.console.print("[red]Ungültige Eingabe[/red]")
                continue

    def _render_numbered_list(self, title: str, items: list[str]) -> None:
        table = Table(title=title, show_header=False, box=None, padding=(0, 2))
        table.add_column(style="bold cyan", width=3)
        table.add_column()
        for i, item in enumerate(items, 1):
            table.add_row(f"{i}.", item)
        self.console.print(table)


def print_summary(profile, posts_count: int) -> None:
    """Hilfsfunktion am Ende des Wizards."""
    c = Console()
    md = (
        f"# ✓ Onboarding abgeschlossen\n\n"
        f"**Profil:** `{profile.profile_id}`\n\n"
        f"- Name: {profile.client.name}\n"
        f"- Themen: {len(profile.client.topics)}\n"
        f"- Audience-Block: {'✓' if profile.audience.description else '—'}\n"
        f"- Erfolgreichste Posts (Stil-Anker): {len(profile.successful_posts)}\n"
        f"- Posts in Sidecar: {posts_count}\n"
        f"- Personas: {len(profile.personas)}\n"
        f"- NoGos: {len(profile.nogos)}\n"
    )
    c.print(Panel(Markdown(md), border_style="green"))


def main_error(msg: str) -> None:
    Console(stderr=True).print(f"[red bold]Fehler:[/red bold] {msg}")
