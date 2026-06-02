"""Generiert nachträglich Kunden-Avatare (Personas) für ein bestehendes Profil.

Nutzt denselben PersonasStep wie der Onboarding-Wizard — d.h. exakt die gleiche
Prompt-Logik und derselbe Output-Parser. Anschliessend wird das Profil mit
den neuen Personas zurückgeschrieben.

Aufruf:
    uv run python -m apps.dev.generate_personas                  # Default-Profil
    uv run python -m apps.dev.generate_personas --profile danny  # Spezifisches Profil
    uv run python -m apps.dev.generate_personas --force          # Existierende Personas überschreiben
"""

from __future__ import annotations

from eve.utils.windows_console import enable_utf8_console

enable_utf8_console()

import argparse  # noqa: E402
import asyncio  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402

from apps.dev.preview_prompts import render_verification  # noqa: E402
from apps.onboarding.rich_ui import RichCliWizardUI  # noqa: E402
from eve.adapters.llm.anthropic_provider import AnthropicProvider  # noqa: E402
from eve.adapters.persistence.fs_prompt_repository import FilesystemPromptRepository  # noqa: E402
from eve.config import get_settings  # noqa: E402
from eve.use_cases.onboarding.state import WizardState  # noqa: E402
from eve.use_cases.onboarding.steps.step_06_personas import PersonasStep  # noqa: E402
from eve.use_cases.profile_verification import verify_profile_assets  # noqa: E402


async def run(profile_id: str | None, *, force: bool) -> int:
    console = Console()

    project_root = Path(__file__).resolve().parents[2]
    prompts = FilesystemPromptRepository(base_dir=project_root / "prompts")

    # --- 1. Verifizieren, dass das Profil existiert + alle benötigten Felder hat ---
    try:
        result = await verify_profile_assets(prompts, profile_id)
    except KeyError as e:
        console.print(f"[red bold]Fehler:[/red bold] {e}")
        return 1
    render_verification(console, result)
    profile_id = result.profile_id  # resolved default

    if result.has_errors:
        console.print(
            "\n[red bold]Abbruch:[/red bold] Es fehlen Pflicht-Assets. "
            "Personas-Generierung würde sinnlos laufen.\n"
        )
        return 1

    # --- 2. Profil laden + prüfen ob bereits Personas existieren ---
    profile = await prompts.get_profile(profile_id)

    if not profile.audience.description:
        console.print(
            "[red bold]Fehler:[/red bold] Profil hat keine Audience-Beschreibung. "
            "Bitte erst manuell im YAML ergänzen oder den Wizard neu durchlaufen."
        )
        return 1

    if profile.personas and not force:
        console.print(
            Panel(
                f"Profil hat bereits [bold]{len(profile.personas)}[/bold] Persona(s):\n\n"
                + "\n".join(f"  • {p.name}: {p.role[:80]}…" for p in profile.personas)
                + "\n\nNutze [bold]--force[/bold] um zu überschreiben.",
                title="[yellow]Personas existieren bereits",
                border_style="yellow",
            )
        )
        return 0

    # --- 3. LLM-Provider initialisieren ---
    settings = get_settings()
    if not settings.anthropic_api_key:
        console.print("[red bold]Fehler:[/red bold] ANTHROPIC_API_KEY fehlt in .env.")
        return 1
    llm = AnthropicProvider(api_key=settings.anthropic_api_key.get_secret_value())

    # --- 4. PersonasStep standalone laufen lassen ---
    ui = RichCliWizardUI(console=console)
    state = WizardState(profile_id=profile_id, profile=profile)

    step = PersonasStep(ui, llm, prompts, model=settings.llm_default_model)
    state = await step.run(state)

    if not state.profile.personas:
        console.print(
            "[red bold]Fehler:[/red bold] Es wurden keine Personas erzeugt. "
            "(LLM-Output konnte nicht geparst werden)"
        )
        return 1

    # --- 5. Zurückspeichern ---
    saved = await prompts.save_profile(state.profile)
    console.print(
        Panel(
            f"✓ {len(saved.personas)} Persona(s) gespeichert:\n\n"
            + "\n\n".join(
                f"[bold magenta]{p.name}[/bold magenta]\n"
                f"  Role: {p.role[:200]}{'…' if len(p.role) > 200 else ''}\n"
                f"  Organization: {p.organization[:150]}"
                f"{'…' if len(p.organization) > 150 else ''}"
                for p in saved.personas
            )
            + f"\n\n[dim]Profil-Datei: prompts/profiles/{saved.profile_id}.yaml[/dim]",
            title="[green]Personas generiert",
            border_style="green",
        )
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Generiert Kunden-Avatare für ein bestehendes Profil")
    parser.add_argument("--profile", default=None, help="Profile-ID (default: Default-Profil)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Existierende Personas überschreiben",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    sys.exit(asyncio.run(run(args.profile, force=args.force)))


if __name__ == "__main__":
    main()
