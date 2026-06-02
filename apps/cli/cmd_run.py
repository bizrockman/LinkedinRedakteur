"""eve run — Hauptprozess für Eve.

Modi:
    chat       — CLI-Chat-Loop mit echtem EveAgent (Stage 2)
    telegram   — Telegram-Bot + Scheduler (Stage 4)
    scheduler  — Nur Auto-Post-Job (Stage 3)
    all        — Telegram + Scheduler + (optional) CLI

Persistenz: wenn SUPABASE_URL + SUPABASE_SERVICE_KEY gesetzt sind, werden
Posts + Chat-History in Supabase persistiert (eve_posts / eve_chat_histories)
und Bilder in den Storage-Bucket migriert. Sonst Filesystem-Sidecar +
In-Memory-History als Fallback.
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
from eve.adapters.persistence.fs_posts_repository import FilesystemPostsRepository
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
from eve.core.ports import ChatMemory, FileStorage, PostsRepository
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
    """CLI-Chat mit echtem EveAgent (Anthropic + Tools + Persistenz)."""
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

    # --- Persistence wiren (Supabase wenn da, sonst Filesystem-Fallback)
    supabase_client = _try_create_supabase_client(settings, console)
    posts_repo, persistence_label = _build_posts_repository(supabase_client, prompts)
    chat_memory, memory_label = _build_chat_memory(supabase_client, resolved_profile_id)
    file_storage, storage_label = _build_file_storage(supabase_client)

    # --- LLM + Agent
    llm = AnthropicProvider(api_key=settings.anthropic_api_key.get_secret_value())

    tools = ToolRegistry(
        [
            NowTool(),
            FetchUrlTool(),
            SearchPostsTool(posts_repo, resolved_profile_id),
            CreatePostTool(posts_repo, resolved_profile_id),
            UpdatePostTool(posts_repo, resolved_profile_id),
            EvaluateWithPersonaTool(
                prompts, llm, resolved_profile_id,
                model=settings.llm_default_model,
            ),
        ]
    )

    image_tool = _build_image_tool_if_configured(settings, console, file_storage)
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

    cli_messenger = CLIMessenger(console=console, eve_name="Eve")
    router = MessageRouter()
    router.register(cli_messenger)

    console.print(
        Panel(
            f"[bold]Eve Chat[/bold] — Profil: [cyan]{resolved_profile_id}[/cyan]\n"
            f"[dim]Posts:      {persistence_label}\n"
            f"History:    {memory_label}\n"
            f"Storage:    {storage_label}\n"
            f"Tools:      {', '.join(tools.names)}\n"
            f"Modell:     {settings.llm_default_model}[/dim]\n\n"
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


# ----------------------------------------------------------------------
# Wire-Helpers
# ----------------------------------------------------------------------
def _try_create_supabase_client(settings, console):
    if not settings.supabase_url or not settings.supabase_service_key:
        return None
    try:
        from supabase import create_client

        return create_client(
            settings.supabase_url,
            settings.supabase_service_key.get_secret_value(),
        )
    except Exception as e:
        console.print(f"[yellow]Supabase-Client-Aufbau fehlgeschlagen: {e}[/yellow]")
        return None


def _build_posts_repository(
    supabase_client, prompts
) -> tuple[PostsRepository, str]:
    if supabase_client is not None:
        from eve.adapters.persistence.supabase_posts_repository import (
            SupabasePostsRepository,
        )

        return SupabasePostsRepository(supabase_client), "Supabase (eve_posts)"
    return FilesystemPostsRepository(prompts), "Filesystem (JSON-Sidecar)"


def _build_chat_memory(supabase_client, profile_id: str) -> tuple[ChatMemory, str]:
    if supabase_client is not None:
        from eve.adapters.persistence.supabase_chat_memory import SupabaseChatMemory

        return (
            SupabaseChatMemory(supabase_client, profile_id=profile_id),
            "Supabase (eve_chat_histories)",
        )
    return InMemoryChatMemory(), "In-Memory (verschwindet bei Exit)"


def _build_file_storage(supabase_client) -> tuple[FileStorage | None, str]:
    if supabase_client is None:
        return None, "kein Supabase, Bilder bleiben auf fal.ai-CDN"
    from eve.adapters.persistence.supabase_storage import SupabaseStorageAdapter

    return SupabaseStorageAdapter(supabase_client), "Supabase Storage (Bilder werden migriert)"


def _build_image_tool_if_configured(
    settings, console: Console, file_storage: FileStorage | None
) -> GenerateImageTool | None:
    """Baut GenerateImageTool nur wenn fal.ai konfiguriert.

    file_storage ist optional — wenn None, bleibt Bild auf fal.ai-CDN (24h).
    """
    if not settings.fal_api_key:
        console.print("[dim]· Image-Tool deaktiviert (FAL_API_KEY fehlt)[/dim]")
        return None
    if not settings.supabase_url or not settings.supabase_service_key:
        console.print(
            "[dim]· Image-Tool deaktiviert "
            "(SUPABASE_URL/SUPABASE_SERVICE_KEY fehlt — "
            "References kommen aus Storage)[/dim]"
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
    return GenerateImageTool(
        generator,
        storage=file_storage,
        bucket=settings.supabase_storage_bucket,
    )


def main_sync() -> None:
    import sys

    logging.basicConfig(level=logging.INFO)
    sys.exit(asyncio.run(run_main_process(mode="chat", profile_id=None)))


if __name__ == "__main__":
    main_sync()
