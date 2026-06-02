"""eve profile <subcommand> — Profil verifizieren, Prompts vorschauen, Personas generieren."""

from __future__ import annotations

import asyncio

import typer

from apps.dev import generate_personas, preview_prompts

app = typer.Typer(no_args_is_help=True)


@app.command()
def preview(
    profile: str = typer.Option(None, "--profile", "-p", help="Profil-ID"),
    only: str = typer.Option(None, "--only", help="eve | persona"),
    skip_verify: bool = typer.Option(False, "--no-verify"),
) -> None:
    """Zeigt die finalen System-Prompts (Eve + Persona) gegen ein Profil."""
    raise typer.Exit(
        code=asyncio.run(preview_prompts.main(profile, only, skip_verify=skip_verify))
    )


@app.command()
def personas(
    profile: str = typer.Option(None, "--profile", "-p", help="Profil-ID"),
    force: bool = typer.Option(False, "--force", help="Existierende Personas überschreiben"),
) -> None:
    """Generiert Kunden-Avatare nachträglich für ein bestehendes Profil."""
    raise typer.Exit(code=asyncio.run(generate_personas.run(profile, force=force)))


@app.command()
def verify(
    profile: str = typer.Option(None, "--profile", "-p", help="Profil-ID"),
) -> None:
    """Verifiziert alle Assets eines Profils (Tabelle mit Status-Glyphs)."""

    async def _run() -> int:
        from pathlib import Path

        from rich.console import Console

        from apps.dev.preview_prompts import render_verification
        from eve.adapters.persistence.fs_prompt_repository import FilesystemPromptRepository
        from eve.use_cases.profile_verification import verify_profile_assets

        console = Console()
        project_root = Path(__file__).resolve().parents[2]
        repo = FilesystemPromptRepository(base_dir=project_root / "prompts")

        try:
            result = await verify_profile_assets(repo, profile)
        except KeyError as e:
            console.print(f"[red bold]Fehler:[/red bold] {e}")
            return 1
        render_verification(console, result)
        return 1 if result.has_errors else 0

    raise typer.Exit(code=asyncio.run(_run()))
