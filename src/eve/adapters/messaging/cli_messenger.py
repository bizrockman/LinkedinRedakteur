"""CLIMessenger — MessagingProvider, der via Rich-Console schreibt.

Erste Implementation des MessagingProvider-Ports. Lässt sich genauso wie
ein Telegram-Bot vom MessageRouter ansprechen — nur dass die Antwort halt
auf stdout landet statt in einem Chat.
"""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from eve.core.entities import MessageSource


class CLIMessenger:
    """Implementiert MessagingProvider Protocol via Rich-Console."""

    def __init__(self, console: Console | None = None, *, eve_name: str = "Eve") -> None:
        self.console = console or Console()
        self.eve_name = eve_name

    @property
    def source(self) -> MessageSource:
        return MessageSource.CLI

    async def send_text(
        self, *, chat_id: str, text: str, reply_to: str | None = None
    ) -> None:
        self.console.print(
            Panel(
                Markdown(text),
                title=f"[bold magenta]{self.eve_name}",
                border_style="magenta",
                padding=(0, 1),
            )
        )

    async def send_image(
        self,
        *,
        chat_id: str,
        image_url: str,
        caption: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        body = (caption + "\n\n") if caption else ""
        body += f"[link={image_url}]{image_url}[/link]"
        self.console.print(
            Panel(
                body,
                title=f"[bold magenta]{self.eve_name}[/bold magenta] [dim](image)[/dim]",
                border_style="magenta",
                padding=(0, 1),
            )
        )
