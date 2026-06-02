"""eve db <subcommand> — wrapper um apps.dev.db_setup."""

from __future__ import annotations

import asyncio

import typer

from apps.dev import db_setup

app = typer.Typer(no_args_is_help=True)


@app.command()
def check() -> None:
    """Smoke-Test gegen Supabase: Verbindung + Bucket + References + Tabelle."""
    args = type("A", (), {"command": "check"})()
    raise typer.Exit(code=asyncio.run(db_setup.main(args)))


@app.command()
def migrate(
    open_browser: bool = typer.Option(False, "--open", help="Dashboard im Browser öffnen"),
) -> None:
    """Zeigt Migrations + Deep-Link zum Supabase SQL Editor."""
    args = type("A", (), {"command": "migrate", "open": open_browser, "file": None})()
    raise typer.Exit(code=asyncio.run(db_setup.main(args)))


@app.command(name="print")
def cmd_print(
    file: str = typer.Option(None, "--file", "-f", help="Welche SQL-Datei (default: erste)"),
    plain: bool = typer.Option(
        False, "--plain", help="Reines SQL ohne Highlighting (für Copy-Paste oder Datei-Redirect)"
    ),
) -> None:
    """Druckt eine Migration zum Copy-Paste in den SQL Editor."""
    args = type("A", (), {"command": "print", "file": file, "plain": plain, "open": False})()
    raise typer.Exit(code=asyncio.run(db_setup.main(args)))
