"""Renders Eve's system prompts gegen ein gespeichertes Profil — zum Reviewen.

Aufruf:
    uv run python -m apps.dev.preview_prompts                  # default-profile, beide Prompts
    uv run python -m apps.dev.preview_prompts --profile danny  # spezifisches Profil
    uv run python -m apps.dev.preview_prompts --only eve       # nur eve_system
    uv run python -m apps.dev.preview_prompts --only persona   # nur persona (für jede Persona im Profil)
"""

from __future__ import annotations

from eve.utils.windows_console import enable_utf8_console

enable_utf8_console()

import argparse  # noqa: E402
import asyncio  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.rule import Rule  # noqa: E402
from rich.table import Table  # noqa: E402

from eve.adapters.persistence.fs_prompt_repository import FilesystemPromptRepository  # noqa: E402
from eve.use_cases.profile_verification import (  # noqa: E402
    ProfileVerificationResult,
    verify_profile_assets,
)

STATUS_GLYPH = {"ok": "[green]✓[/green]", "warn": "[yellow]![/yellow]", "missing": "[red]✗[/red]"}


def render_verification(console: Console, result: ProfileVerificationResult) -> None:
    table = Table(
        title=(
            f"Profile Assets — '{result.profile_id}'"
            f"{'  (default)' if result.is_default else ''}"
        ),
        show_header=True,
        title_style="bold cyan",
    )
    table.add_column("", width=2)
    table.add_column("Asset", style="bold")
    table.add_column("Status")
    table.add_column("Detail", style="dim")

    for c in result.checks:
        table.add_row(STATUS_GLYPH[c.status], c.name, c.status.upper(), c.detail)
    console.print(table)


async def render_eve(repo: FilesystemPromptRepository, profile_id: str | None) -> str:
    now = datetime.now()
    rendered = await repo.render(
        "eve_system",
        profile_id=profile_id,
        extra_context={
            "now_weekday": now.strftime("%A"),
            "now_week": now.isocalendar().week,
            "now_iso": now.isoformat(),
        },
    )
    return rendered.body


async def render_persona(
    repo: FilesystemPromptRepository,
    profile_id: str | None,
    persona_index: int = 0,
) -> tuple[str, str]:
    """Returns (persona_name, rendered_prompt)."""
    profile = await repo.get_profile(profile_id)
    if not profile.personas:
        return ("(none)", "Keine Personas im Profil definiert.")
    persona = profile.personas[persona_index]
    rendered = await repo.render(
        "persona",
        profile_id=profile_id,
        extra_context={"persona": persona},
    )
    return (persona.name, rendered.body)


async def main(profile_id: str | None, only: str | None, *, skip_verify: bool) -> None:
    console = Console()

    project_root = Path(__file__).resolve().parents[2]
    repo = FilesystemPromptRepository(base_dir=project_root / "prompts")

    # --- Verification (außer explizit ausgeschaltet) ---
    if not skip_verify:
        try:
            result = await verify_profile_assets(repo, profile_id)
        except KeyError as e:
            console.print(f"[red bold]Fehler:[/red bold] {e}")
            return
        render_verification(console, result)
        profile_id = result.profile_id  # Resolved Default

        if result.has_errors:
            console.print(
                "\n[red bold]Abbruch:[/red bold] Es fehlen Pflicht-Assets. "
                "Behebe die [red]✗[/red]-Einträge oben (oder nutze --no-verify zum Erzwingen).\n"
            )
            return

        if result.has_warnings:
            console.print(
                "\n[yellow]Hinweis:[/yellow] Es gibt Warnungen ([yellow]![/yellow]). "
                "Rendering läuft trotzdem.\n"
            )
    else:
        # Verification übersprungen — wir müssen profile_id selbst auflösen
        if profile_id is None:
            profile_id = await repo.get_default_profile_id()
            if profile_id is None:
                console.print("[red]Kein Default-Profil gesetzt. Nutze --profile X[/red]")
                return

    console.print(Rule(f"[bold cyan]Profile: {profile_id}"))

    if only in (None, "eve"):
        eve_body = await render_eve(repo, profile_id)
        console.print(
            Panel(
                eve_body,
                title=f"[bold]eve_system  ({len(eve_body)} chars)",
                border_style="green",
            )
        )

    if only in (None, "persona"):
        profile = await repo.get_profile(profile_id)
        if not profile.personas:
            console.print("[yellow]Keine Personas im Profil definiert.[/yellow]")
            return
        for idx, _persona in enumerate(profile.personas):
            name, body = await render_persona(repo, profile_id, persona_index=idx)
            console.print(
                Panel(
                    body,
                    title=f"[bold]persona[{idx}] = {name}  ({len(body)} chars)",
                    border_style="magenta",
                )
            )


def cli() -> None:
    parser = argparse.ArgumentParser(description="Vorschau Eve's System-Prompts")
    parser.add_argument("--profile", default=None, help="Profile-ID (default: Default-Profil)")
    parser.add_argument(
        "--only",
        choices=["eve", "persona"],
        default=None,
        help="Nur ein Template rendern (default: beide)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Asset-Verifikation überspringen",
    )
    args = parser.parse_args()
    asyncio.run(main(args.profile, args.only, skip_verify=args.no_verify))


if __name__ == "__main__":
    cli()
