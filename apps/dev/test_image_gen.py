"""Testet die fal.ai Image-Generation End-to-End.

Standardmäßig nutzt es den Astronauten-Prompt aus dem n8n-Workflow als
Demo-Test. Mit `--prompt "..."` oder `--prompt-file path/to/prompt.txt`
kannst du eigene Prompts testen.

Aufruf:
    uv run python -m apps.dev.test_image_gen
    uv run python -m apps.dev.test_image_gen --prompt "Ein futuristisches Büro mit der Person aus den Referenzen am Whiteboard"
    uv run python -m apps.dev.test_image_gen --open    # öffnet die URL im Browser
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
from supabase import create_client  # noqa: E402

from eve.adapters.images.fal_seedream import FalSeedreamGenerator  # noqa: E402
from eve.config import get_settings  # noqa: E402

# n8n-Default aus pinData "Lego - Manni2" → "Image Generation" Sub-Workflow.
# Tested viele Aspekte: Identitäts-Erhaltung, komplexe Outfit-Beschreibung,
# spezifisches Lighting-Setup, Kamera-Parameter.
DEFAULT_PROMPT = """\
A cinematic medium close-up portrait of the same person from the reference image — preserve identity exactly.
The person is wearing a highly detailed futuristic astronaut suit design, retro-futuristic yet functional.

The suit is bulky and protective with segmented layers, soft pastel white and dusty grey fabric panels reinforced with metallic details. Visible pressure-sealed rings at the neck, wrists, and joints. The chest features a life-support control module with dials, tubing, and subtle illuminated indicators. The suit is multi-layered: an outer thermal shell with fabric creases and rugged texture, underneath reinforced layers for pressure and insulation. The neck ring is matte metallic, designed to lock into a helmet. The overall design looks functional but cinematic, mixing realism with slight sci-fi aesthetics.

Setting: Ambient lit cockpit interior of a spaceship with blurred digital control panels in the background. The atmosphere is dreamy and futuristic. The person and the suit are illuminated by harsh cyan rim lighting on one side and harsh magenta rim lighting on the other, which fades into shades of purple. Soft, yellowish 3200K front lighting.

Vibe: confident, calm, optimistic.

Colour grading: magenta-cyan complementary palette with violet transitions, cinematic diffusion glow, subtle film grain, photorealistic, ultra-detailed, high quality.

Camera setup: Cinematic portrait photography, medium close-up framing at eye level, shot on an 85mm lens with aperture f/1.4. Shallow depth of field with creamy smooth bokeh, background softly blurred, subject's eyes in tack-sharp focus. Natural skin texture rendered in ultra detail, cinematic diffusion glow, filmic colour grading with balanced contrast. Subtle vignette, high dynamic range, 8K, photorealistic quality.\
"""


async def run(prompt: str, *, open_browser: bool, model: str | None) -> int:
    console = Console()
    settings = get_settings()

    # Credentials-Check
    missing: list[str] = []
    if not settings.fal_api_key:
        missing.append("FAL_API_KEY")
    if not settings.supabase_url or not settings.supabase_service_key:
        missing.append("SUPABASE_URL + SUPABASE_SERVICE_KEY")
    if missing:
        console.print(
            Panel(
                f"[red bold]Fehlt in .env:[/red bold] {', '.join(missing)}\n\n"
                "FAL_API_KEY: [link]https://fal.ai/dashboard/keys[/link]\n"
                "Supabase: Dashboard → Settings → API",
                title="[yellow]Konfiguration",
                border_style="yellow",
            )
        )
        return 1

    # Supabase-Client für Reference-Listing
    supabase = create_client(
        settings.supabase_url,
        settings.supabase_service_key.get_secret_value(),
    )
    chosen_model = model or settings.fal_image_model
    generator = FalSeedreamGenerator(
        api_key=settings.fal_api_key.get_secret_value(),
        model=chosen_model,
        supabase_client=supabase,
        bucket=settings.supabase_storage_bucket,
        references_path=settings.fal_references_path,
    )
    console.print(f"[dim]Modell: {chosen_model}[/dim]")

    # References vorab auflisten — damit der User sieht, womit gearbeitet wird
    references = generator.list_references()
    if references:
        console.print(f"[green]✓[/green] {len(references)} Referenz-Bilder geladen")
        for url in references[:5]:
            console.print(f"  [dim]• {url[:90]}…[/dim]")
        if len(references) > 5:
            console.print(f"  [dim]+ {len(references) - 5} weitere[/dim]")
    else:
        console.print(
            "[yellow]![/yellow] Keine Referenz-Bilder im Bucket — Identität "
            "wird nicht erhalten. Trotzdem fortfahren?"
        )

    console.print()
    console.print(Panel(prompt[:500] + ("…" if len(prompt) > 500 else ""), title="Prompt", border_style="cyan"))
    console.print()

    with console.status("[cyan]fal.ai erzeugt Bild... (kann 30-90s dauern)", spinner="dots"):
        try:
            result = await generator.generate(prompt=prompt)
        except Exception as e:
            console.print(f"[red bold]Generation fehlgeschlagen:[/red bold] {type(e).__name__}: {e}")
            return 1

    sent_urls = result.metadata.get("reference_urls", [])
    urls_block = (
        "\n".join(f"  [dim]{i + 1}. {u}[/dim]" for i, u in enumerate(sent_urls))
        if sent_urls else "  [dim](keine)[/dim]"
    )
    console.print(
        Panel(
            f"[bold]URL:[/bold] {result.url}\n\n"
            f"[dim]Modell: {result.model}\n"
            f"Request-ID: {result.metadata.get('request_id', '-')}[/dim]\n\n"
            f"[bold]Tatsächlich an fal.ai gesendete References ({len(sent_urls)}):[/bold]\n"
            f"{urls_block}",
            title="[green]✓ Bild generiert",
            border_style="green",
        )
    )

    if open_browser:
        webbrowser.open(result.url)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="fal.ai Image-Generation Test")
    parser.add_argument("--prompt", default=None, help="Eigener Prompt (sonst Astronaut-Default)")
    parser.add_argument("--prompt-file", type=Path, default=None, help="Prompt aus Datei lesen")
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "fal.ai Modell. Default aus FAL_IMAGE_MODEL. Beispiele:\n"
            "  fal-ai/bytedance/seedream/v4.5/edit  (default — gut für Identitäts-Erhaltung)\n"
            "  fal-ai/nano-banana/edit               (Googles Gemini-basiert)\n"
            "  fal-ai/nano-banana-pro/edit           (höhere Qualität, teurer)"
        ),
    )
    parser.add_argument("--open", action="store_true", help="Bild-URL im Browser öffnen")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8")
    elif args.prompt:
        prompt = args.prompt
    else:
        prompt = DEFAULT_PROMPT

    sys.exit(asyncio.run(run(prompt, open_browser=args.open, model=args.model)))


if __name__ == "__main__":
    main()
