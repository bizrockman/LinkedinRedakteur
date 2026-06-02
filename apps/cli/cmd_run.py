"""eve run — Hauptprozess für Eve.

Modi:
    chat       — CLI-Chat-Loop mit echtem EveAgent (Stage 2)
    telegram   — Telegram-Bot + Scheduler (Stage 4)
    scheduler  — Nur Auto-Post-Job (Stage 3)
    all        — Telegram + Scheduler + (optional) CLI
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from eve.adapters.llm.anthropic_provider import AnthropicProvider
from eve.adapters.messaging.cli_messenger import CLIMessenger
from eve.adapters.persistence.fs_prompt_repository import FilesystemPromptRepository
from eve.adapters.persistence.in_memory_chat_memory import InMemoryChatMemory
from eve.agent.agent import EveAgent
from eve.agent.tools import (
    CreatePostTool,
    EvaluateWithPersonaTool,
    FetchUrlTool,
    GenerateImageTool,
    NowTool,
    SearchPostsTool,
    ToolRegistry,
    UpdatePostTool,
)
from eve.config import get_settings
from eve.core.entities import IncomingMessage, MessageSource
from eve.use_cases.message_router import MessageRouter

log = logging.getLogger(__name__)


async def run_main_process(*, mode: str, profile_id: str | None) -> int:
    console = Console()

    if mode == "chat":
        return await _run_chat_mode(console, profile_id)
    if mode == "telegram":
        console.print("[yellow]telegram-mode noch nicht implementiert (Stage 4).[/yellow]")
        return 2
    if mode == "scheduler":
        console.print("[yellow]scheduler-mode noch nicht implementiert (Stage 3).[/yellow]")
        return 2
    if mode == "all":
        console.print("[yellow]all-mode noch nicht implementiert (kombiniert Stage 3+4).[/yellow]")
        return 2

    console.print(f"[red]Unbekannter Modus: {mode}[/red]")
    return 1


async def _run_chat_mode(console: Console, profile_id: str | None) -> int:
    """CLI-Chat mit echtem EveAgent (Anthropic + Tools + In-Memory History)."""
    # --- Credentials prüfen
    settings = get_settings()
    if not settings.anthropic_api_key:
        console.print(
            Panel(
                "[red bold]ANTHROPIC_API_KEY fehlt in .env.[/red bold]\n\n"
                "Hol dir einen Key: [link]https://console.anthropic.com/[/link]",
                title="[yellow]Konfiguration",
                border_style="yellow",
            )
        )
        return 1

    project_root = Path(__file__).resolve().parents[2]
    prompts = FilesystemPromptRepository(base_dir=project_root / "prompts")

    # Profil resolven
    resolved_profile_id = profile_id
    if resolved_profile_id is None:
        resolved_profile_id = await prompts.get_default_profile_id()
        if resolved_profile_id is None:
            console.print(
                "[red]Kein Default-Profil. Wizard durchlaufen: "
                "[cyan]uv run eve onboard[/cyan][/red]"
            )
            return 1

    # --- Dependencies wiren
    llm = AnthropicProvider(api_key=settings.anthropic_api_key.get_secret_value())
    chat_memory = InMemoryChatMemory()

    tools = ToolRegistry(
        [
            NowTool(),
            FetchUrlTool(),
            SearchPostsTool(prompts, resolved_profile_id),
            CreatePostTool(prompts, resolved_profile_id),
            UpdatePostTool(prompts, resolved_profile_id),
            EvaluateWithPersonaTool(
                prompts, llm, resolved_profile_id,
                model=settings.llm_default_model,
            ),
        ]
    )

    # generate_image-Tool nur aktivieren wenn fal.ai + Supabase voll konfiguriert
    image_tool = _build_image_tool_if_configured(settings, console)
    if image_tool is not None:
        tools.register(image_tool)

    agent = EveAgent(
        llm=llm,
        prompts=prompts,
        chat_memory=chat_memory,
        tools=tools,
        profile_id=resolved_profile_id,
        model=settings.llm_default_model,
    )

    # Messenger + Router
    cli_messenger = CLIMessenger(console=console, eve_name="Eve")
    router = MessageRouter()
    router.register(cli_messenger)

    # --- Greeting
    console.print(
        Panel(
            f"[bold]Eve Chat[/bold] — Profil: [cyan]{resolved_profile_id}[/cyan]\n"
            f"[dim]Tools: {', '.join(tools.names)}[/dim]\n"
            f"[dim]Modell: {settings.llm_default_model}[/dim]\n\n"
            "[dim]Tippe deine Nachricht. Beenden mit leerer Zeile + Enter "
            "oder Strg+C.[/dim]",
            border_style="cyan",
            title="[bold magenta]Eve[/bold magenta]",
        )
    )

    session_id = f"CLI_{resolved_profile_id}"
    turn_count = 0

    try:
        while True:
            user_text = Prompt.ask("[bold cyan]Du")
            if not user_text.strip():
                console.print("[dim]Bye. Bis später![/dim]")
                return 0

            turn_count += 1
            incoming = IncomingMessage(
                source=MessageSource.CLI,
                session_id=session_id,
                user_id="local",
                chat_id="stdout",
                text=user_text,
            )

            with console.status(
                f"[cyan]Eve denkt... (Turn {turn_count})", spinner="dots"
            ):
                try:
                    response = await agent.handle(incoming)
                except Exception as e:
                    log.exception("Agent crash")
                    console.print(
                        f"[red bold]Agent-Fehler:[/red bold] {type(e).__name__}: {e}"
                    )
                    continue

            await router.dispatch(response)
    except KeyboardInterrupt:
        console.print("\n[yellow]Abgebrochen.[/yellow]")
        return 130


def _build_image_tool_if_configured(settings, console: Console) -> GenerateImageTool | None:
    """Baut GenerateImageTool nur wenn fal.ai + Supabase konfiguriert.

    Sonst läuft Eve ohne Image-Gen — alle anderen Tools funktionieren.
    """
    if not settings.fal_api_key:
        console.print("[dim]· Image-Tool deaktiviert (FAL_API_KEY fehlt)[/dim]")
        return None
    if not settings.supabase_url or not settings.supabase_service_key:
        console.print(
            "[dim]· Image-Tool deaktiviert "
            "(SUPABASE_URL/SUPABASE_SERVICE_KEY fehlt — "
            "Reference-Bilder kommen aus Storage)[/dim]"
        )
        return None

    from supabase import create_client

    from eve.adapters.images.fal_seedream import FalSeedreamGenerator

    supabase_client = create_client(
        settings.supabase_url,
        settings.supabase_service_key.get_secret_value(),
    )
    generator = FalSeedreamGenerator(
        api_key=settings.fal_api_key.get_secret_value(),
        model=settings.fal_image_model,
        supabase_client=supabase_client,
        bucket=settings.supabase_storage_bucket,
        references_path=settings.fal_references_path,
    )
    return GenerateImageTool(generator)


def main_sync() -> None:
    """Standalone-Aufruf für `python -m apps.cli.cmd_run`."""
    import sys

    logging.basicConfig(level=logging.INFO)
    sys.exit(asyncio.run(run_main_process(mode="chat", profile_id=None)))


if __name__ == "__main__":
    main_sync()
