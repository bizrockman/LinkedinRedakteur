"""Eve — zentrale CLI.

Alle Helper unter einem Befehl. Aufruf:

    uv run eve --help

Sub-Commands:
    onboard   — Onboarding-Wizard durchlaufen
    db        — Supabase-Setup & Migrations
    profile   — Profil verifizieren, Prompts vorschauen, Personas regenerieren
    image     — fal.ai Image-Generation testen
    run       — Hauptprozess (CLI-Chat / Telegram / Scheduler)
"""

from __future__ import annotations

from eve.utils.windows_console import enable_utf8_console

enable_utf8_console()

import asyncio  # noqa: E402

import typer  # noqa: E402
from rich.console import Console  # noqa: E402

from apps.cli import cmd_db, cmd_image, cmd_onboard, cmd_profile, cmd_run  # noqa: E402

app = typer.Typer(
    name="eve",
    help="Eve — LinkedIn Editorial Agent. Alle Commands in einer CLI.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)

# Sub-Apps registrieren
app.add_typer(cmd_db.app, name="db", help="Supabase-Setup & Migrations")
app.add_typer(cmd_profile.app, name="profile", help="Profil verwalten + verifizieren")
app.add_typer(cmd_image.app, name="image", help="Bildgenerierung testen")


@app.command()
def onboard(
    profile: str = typer.Option(None, "--profile", "-p", help="Profil-ID (default: 'default')"),
    model: str = typer.Option(None, "--model", "-m", help="LLM-Modell (default aus settings)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Onboarding-Wizard durchlaufen (6 Steps)."""
    import logging

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cmd_onboard.run_onboarding(profile_id=profile or "default", model=model)


@app.command()
def run(
    mode: str = typer.Option("chat", "--mode", "-m", help="chat | telegram | scheduler | all"),
    profile: str = typer.Option(None, "--profile", "-p", help="Profil-ID (default: Default-Profil)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Hauptprozess starten."""
    import logging

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    exit_code = asyncio.run(cmd_run.run_main_process(mode=mode, profile_id=profile))
    raise typer.Exit(code=exit_code)


@app.command()
def version() -> None:
    """Zeigt die Eve-Version."""
    from eve import __version__

    Console().print(f"[bold magenta]Eve[/bold magenta] v{__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
