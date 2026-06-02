"""eve image <subcommand> — Test fal.ai Bildgenerierung."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from apps.dev import test_image_gen

app = typer.Typer(no_args_is_help=True)


@app.command()
def test(
    prompt: str = typer.Option(None, "--prompt", help="Eigener Prompt"),
    prompt_file: Path = typer.Option(None, "--prompt-file", help="Prompt aus Datei lesen"),
    model: str = typer.Option(None, "--model", help="Modell-Override (z.B. fal-ai/nano-banana/edit)"),
    open_browser: bool = typer.Option(False, "--open", help="Resultat im Browser öffnen"),
) -> None:
    """Generiert ein Test-Bild via fal.ai (Default: Astronaut-Prompt aus n8n)."""
    if prompt_file:
        body = prompt_file.read_text(encoding="utf-8")
    elif prompt:
        body = prompt
    else:
        body = test_image_gen.DEFAULT_PROMPT
    raise typer.Exit(code=asyncio.run(test_image_gen.run(body, open_browser=open_browser, model=model)))
