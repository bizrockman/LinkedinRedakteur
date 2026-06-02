"""Supabase Setup-CLI für Eve.

Eve nutzt den offiziellen `supabase-py` Client — du brauchst nur:
    SUPABASE_URL         = https://<ref>.supabase.co
    SUPABASE_SERVICE_KEY = service_role JWT  ODER  sb_secret_xxx

Sub-Commands:
    check    — Smoke-Test: Client kann sich verbinden + Storage-Bucket vorhanden?
    migrate  — Zeigt die SQL-Migrations + Dashboard-Link zum SQL Editor
    print    — Druckt die SQL-Files in den Terminal (für Copy-Paste)

Aufruf:
    uv run python -m apps.dev.db_setup check
    uv run python -m apps.dev.db_setup migrate
"""

from __future__ import annotations

from eve.utils.windows_console import enable_utf8_console

enable_utf8_console()

import argparse  # noqa: E402
import asyncio  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
import webbrowser  # noqa: E402
from pathlib import Path  # noqa: E402

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.syntax import Syntax  # noqa: E402
from rich.table import Table  # noqa: E402
from supabase import create_client  # noqa: E402

from eve.config import get_settings  # noqa: E402
from eve.use_cases.db_migrations import (  # noqa: E402
    dashboard_sql_editor_url,
    discover_all_migrations,
    discover_migrations,
)


def _ensure_credentials(console: Console) -> tuple[str, str] | None:
    """Holt SUPABASE_URL + SUPABASE_SERVICE_KEY; zeigt sonst hilfreichen Hint."""
    settings = get_settings()
    url = settings.supabase_url.strip()
    key_secret = settings.supabase_service_key
    key = key_secret.get_secret_value() if key_secret else ""

    missing: list[str] = []
    if not url or "[PROJECT-REF]" in url:
        missing.append("SUPABASE_URL")
    if not key:
        missing.append("SUPABASE_SERVICE_KEY")

    if missing:
        console.print(
            Panel(
                f"[red bold]Fehlt in .env:[/red bold] {', '.join(missing)}\n\n"
                "Hol dir beides aus dem Supabase-Dashboard:\n"
                "  [link]https://supabase.com/dashboard[/link] → Project → Settings → API\n\n"
                "  • [bold]Project URL[/bold] → SUPABASE_URL\n"
                "  • [bold]Service role[/bold] (JWT) ODER [bold]Secret key[/bold] (sb_secret_...)\n"
                "    → SUPABASE_SERVICE_KEY\n\n"
                "Beide Key-Formate funktionieren.",
                title="[yellow]Konfiguration fehlt",
                border_style="yellow",
            )
        )
        return None

    return url, key


def cmd_check(console: Console, url: str, key: str) -> int:
    """Smoke-Test: Client baut Verbindung auf, Storage-Bucket existiert."""
    try:
        client = create_client(url, key)
    except Exception as e:
        console.print(f"[red bold]create_client fehlgeschlagen:[/red bold] {e}")
        return 1

    console.print(f"[dim]Verbunden mit:[/dim] {url}")
    settings = get_settings()
    ref = settings.supabase_project_ref or "<self-host>"
    console.print(f"[dim]Project-Ref:[/dim] {ref}")

    # Storage-Bucket-Check
    bucket = settings.supabase_storage_bucket
    try:
        buckets = client.storage.list_buckets()
        names = [b.name for b in buckets]
        if bucket not in names:
            console.print(
                f"[yellow]![/yellow] Storage-Bucket '{bucket}' [bold]nicht[/bold] vorhanden\n"
                f"  → Im Dashboard anlegen: Storage → New bucket → '{bucket}' (public read)\n"
                f"  Verfügbare Buckets: {names or '(keine)'}"
            )
        else:
            console.print(f"[green]✓[/green] Storage-Bucket '{bucket}' vorhanden")
            # References-Folder prüfen
            ref_path = settings.fal_references_path
            try:
                files = client.storage.from_(bucket).list(ref_path)
                # Supabase liefert leeres Array bei leerem/fehlendem Folder
                images = [
                    f for f in files
                    if not f["name"].startswith(".")
                    and any(f["name"].lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp"))
                ]
                if images:
                    console.print(
                        f"[green]✓[/green] References-Folder '{ref_path}/' "
                        f"({len(images)} Bilder)"
                    )
                else:
                    console.print(
                        f"[yellow]![/yellow] References-Folder '{ref_path}/' leer oder fehlt\n"
                        f"  → Bilder hochladen: Dashboard → Storage → '{bucket}' → "
                        f"Folder '{ref_path}' → Upload (4-8 Portraits empfohlen)"
                    )
            except Exception as e:
                console.print(
                    f"[yellow]![/yellow] References-Check fehlgeschlagen "
                    f"[dim]({type(e).__name__})[/dim]"
                )
                _ = e
    except Exception as e:
        console.print(f"[red bold]Storage-Check fehlgeschlagen:[/red bold] {e}")
        return 1

    # Tables-Check via PostgREST (eve_posts muss reachable sein)
    try:
        client.table("eve_posts").select("id").limit(1).execute()
        console.print("[green]✓[/green] Tabelle 'eve_posts' erreichbar")
        return 0
    except Exception as e:
        console.print(
            "[yellow]![/yellow] Tabelle 'eve_posts' nicht erreichbar\n"
            "  → Migration anwenden: "
            "[cyan]uv run python -m apps.dev.db_setup migrate[/cyan]\n"
            f"  [dim]({type(e).__name__}: {str(e)[:80]})[/dim]"
        )
        return 0  # nicht-fatal


def cmd_migrate(console: Console, *, open_browser: bool) -> int:
    """Zeigt das Setup-SQL + Deep-Link zum Dashboard SQL Editor."""
    project_root = Path(__file__).resolve().parents[2]
    migrations = discover_migrations(project_root / "migrations")

    if not migrations:
        console.print("[yellow]Keine Migrations gefunden in migrations/[/yellow]")
        return 1

    settings = get_settings()
    ref = settings.supabase_project_ref
    if not ref:
        console.print(
            "[yellow]SUPABASE_URL ist Self-Host — kein Dashboard-Link.[/yellow]\n"
            "Wende das SQL manuell auf deiner Self-Host-Instanz an."
        )

    table = Table(title="Setup-SQL", show_header=True)
    table.add_column("", style="bold cyan", width=2)
    table.add_column("Datei", style="bold")
    table.add_column("Zeilen", justify="right")

    for m in migrations:
        line_count = m.content.count("\n")
        table.add_row("→", m.filename, str(line_count))
    console.print(table)

    main_file = migrations[0].filename

    if ref:
        url = dashboard_sql_editor_url(ref)
        console.print(
            Panel(
                f"So setzt du das Schema auf (einmalig, dauert ~10 Sekunden):\n\n"
                f"  [bold]1.[/bold] SQL-Editor öffnen:\n"
                f"     [link]{url}[/link]\n\n"
                f"  [bold]2.[/bold] SQL ins Clipboard:\n"
                f"     [cyan]uv run eve db print --plain[/cyan]\n"
                f"     (alternativ direkt im Terminal anschauen: "
                f"[cyan]uv run eve db print[/cyan])\n\n"
                f"  [bold]3.[/bold] Im SQL Editor pasten + [bold]Run[/bold] klicken\n\n"
                f"Das Setup ist [bold]idempotent[/bold] — kannst du mehrmals laufen lassen, "
                f"ohne dass etwas kaputt geht.",
                title=f"[bold]Setup-Anleitung — {main_file}",
                border_style="cyan",
            )
        )
        if open_browser:
            console.print(f"[dim]Öffne Browser → {url}[/dim]")
            webbrowser.open(url)

    return 0


def cmd_print(console: Console, filename: str | None, *, plain: bool, show_all: bool) -> int:
    """Druckt eine SQL-Datei zum Copy-Paste in den SQL Editor."""
    project_root = Path(__file__).resolve().parents[2]
    pool = (
        discover_all_migrations(project_root / "migrations")
        if show_all or filename is not None
        else discover_migrations(project_root / "migrations")
    )

    if not pool:
        console.print("[yellow]Keine Migrations gefunden.[/yellow]")
        return 1

    target = next((m for m in pool if m.filename == filename), None) if filename else pool[0]
    if target is None:
        console.print(f"[red]Datei '{filename}' nicht gefunden.[/red]")
        console.print("Verfügbar:")
        for m in pool:
            console.print(f"  • {m.filename}")
        return 1

    if plain:
        # Plain mode: nur der SQL-Inhalt, ohne Header/Syntax — direkt copy-paste-able.
        # Auch ideal für Umleitung in eine Datei (uv run ... print --plain > setup.sql).
        print(target.content)
        return 0

    # Pretty mode: Syntax-Highlighting ohne Line-Numbers (sonst killt's den Paste)
    console.print(Panel.fit(target.filename, style="bold cyan"))
    console.print(Syntax(target.content, "sql", theme="monokai", line_numbers=False))
    console.print(
        "[dim]Tipp: für sauberen Paste ohne Rahmen → "
        "[cyan]uv run python -m apps.dev.db_setup print --plain[/cyan][/dim]"
    )
    return 0


async def main(args: argparse.Namespace) -> int:
    console = Console()

    if args.command == "print":
        return cmd_print(
            console, args.file, plain=args.plain, show_all=getattr(args, "all", False)
        )

    creds = _ensure_credentials(console)
    if creds is None:
        return 2
    url, key = creds

    if args.command == "check":
        return cmd_check(console, url, key)
    if args.command == "migrate":
        return cmd_migrate(console, open_browser=args.open)

    console.print(f"[red]Unbekannter Befehl: {args.command}[/red]")
    return 2


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Supabase Setup für Eve (supabase-py basiert)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        choices=["check", "migrate", "print"],
        help="check: Verbindung + Schema testen | migrate: Anweisungen | print: SQL ausgeben",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Bei `print`: welche SQL-Datei (default: erste)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Bei `migrate`: Dashboard im Browser öffnen",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Bei `print`: nur reiner SQL-Text, ohne Rahmen/Highlighting "
        "(ideal für Pipe in Datei)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Bei `print`: zeige auch nummerierte History-Migrations (0001_, 0002_, ...)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    sys.exit(asyncio.run(main(args)))


if __name__ == "__main__":
    cli()
