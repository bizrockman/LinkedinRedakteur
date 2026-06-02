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
    file: str = typer.Option(None, "--file", "-f", help="Welche SQL-Datei (default: main.sql)"),
    plain: bool = typer.Option(
        False, "--plain", help="Reines SQL ohne Highlighting (für Copy-Paste oder Datei-Redirect)"
    ),
    show_all: bool = typer.Option(
        False, "--all", help="Inkl. nummerierter History-Migrations (0001_, 0002_, ...)"
    ),
) -> None:
    """Druckt das Setup-SQL zum Copy-Paste in den Supabase SQL Editor."""
    args = type(
        "A", (), {"command": "print", "file": file, "plain": plain, "open": False, "all": show_all}
    )()
    raise typer.Exit(code=asyncio.run(db_setup.main(args)))
