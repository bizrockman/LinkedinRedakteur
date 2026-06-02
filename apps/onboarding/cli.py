"""Eve Onboarding CLI.

Aufruf:
    uv run python -m apps.onboarding.cli                  # Default-Profil
    uv run python -m apps.onboarding.cli --profile danny  # Benanntes Profil

Logik:
- Wenn das gewünschte Profil existiert: nicht überschreiben, abbrechen
- Sonst: Wizard startet, fragt durch, schreibt prompts/profiles/<id>.yaml
- Erstes gespeichertes Profil wird automatisch Default (FilesystemPromptRepository)
"""

from __future__ import annotations

# UTF-8 fuer Windows-Konsole erzwingen BEVOR irgendetwas anderes geladen wird,
# damit Posts mit Mathematical-Bold-Chars (U+1D400ff.) sauber gerendert werden.
from eve.utils.windows_console import enable_utf8_console

enable_utf8_console()

import argparse  # noqa: E402
import asyncio  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from rich.console import Console  # noqa: E402

from apps.onboarding.rich_ui import RichCliWizardUI, main_error, print_summary  # noqa: E402
from eve.adapters.persistence.fs_prompt_repository import FilesystemPromptRepository  # noqa: E402
from eve.config import get_settings  # noqa: E402
from eve.use_cases.onboarding.wizard import OnboardingWizard  # noqa: E402

DEFAULT_PROFILE_ID = "default"


async def run(profile_id: str, llm_model: str | None) -> int:
    console = Console()

    project_root = Path(__file__).resolve().parents[2]
    prompts = FilesystemPromptRepository(base_dir=project_root / "prompts")

    # Check existence — wir wollen nicht versehentlich überschreiben
    existing = await prompts.list_profiles()
    if profile_id in existing:
        main_error(
            f"Profil '{profile_id}' existiert bereits. Lösche es zuerst "
            f"({project_root / 'prompts' / 'profiles' / f'{profile_id}.yaml'}) "
            f"oder wähle eine andere --profile ID."
        )
        return 1

    # LLM-Provider via Container? Nein, direkt — wir brauchen nur einen.
    settings = get_settings()
    if not settings.anthropic_api_key:
        main_error(
            "ANTHROPIC_API_KEY fehlt in .env. Trag ihn ein und versuch's nochmal."
        )
        return 1

    from eve.adapters.llm.anthropic_provider import AnthropicProvider

    llm = AnthropicProvider(api_key=settings.anthropic_api_key.get_secret_value())
    model = llm_model or settings.llm_default_model

    ui = RichCliWizardUI(console=console)
    wizard = OnboardingWizard(ui=ui, llm=llm, prompts=prompts, llm_model=model)

    try:
        profile = await wizard.run(profile_id)
    except KeyboardInterrupt:
        console.print("\n[yellow]Abgebrochen.[/yellow]")
        return 130
    except Exception as e:
        main_error(f"{type(e).__name__}: {e}")
        logging.exception("Wizard failed")
        return 1

    posts = await prompts.load_posts(profile_id)
    print_summary(profile, posts_count=len(posts))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Eve Onboarding Wizard")
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE_ID,
        help="Profile ID (default: 'default')",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Anthropic Modell für Topic-/Audience-Generierung (default aus settings)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    sys.exit(asyncio.run(run(args.profile, args.model)))


if __name__ == "__main__":
    main()
