"""fetch_url-Tool — lädt eine URL und gibt den lesbaren Text zurück.

Pendant zum n8n `HTTP Request Tool` + `OpenAI Web Search`. Für aktuelle
Infos / Studien / News.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from eve.agent.tools.base import ToolDefinition

log = logging.getLogger(__name__)

MAX_RESPONSE_CHARS = 8000   # Schutz: zu lange Pages würden den Context fluten


class FetchUrlTool:
    """Lädt eine URL via HTTP GET und strippt HTML zu lesbarem Text."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="fetch_url",
            description=(
                "Lädt eine URL (HTTPS) und liefert den lesbaren Text-Inhalt zurück. "
                "Nutze dies, wenn du aktuelle Informationen brauchst — z.B. eine "
                "Studie, einen News-Artikel oder einen Blog-Post. "
                "Limit: max 8000 Zeichen pro Aufruf."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Vollständige URL inkl. https://",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": f"Max. Zeichen zurück (default {MAX_RESPONSE_CHARS})",
                    },
                },
                "required": ["url"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> str:
        url = args.get("url", "").strip()
        if not url or not url.startswith(("http://", "https://")):
            return f"Fehler: ungültige URL '{url}'. Erwartet wird http(s)://..."

        max_chars = int(args.get("max_chars", MAX_RESPONSE_CHARS))

        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; EveBot/1.0; LinkedIn-Editorial-Agent)"
                    ),
                },
            ) as client:
                r = await client.get(url)
                r.raise_for_status()
                content_type = r.headers.get("content-type", "")
                body = r.text
        except httpx.HTTPError as e:
            return f"HTTP-Fehler beim Laden von {url}: {type(e).__name__}: {e}"

        # HTML → Text? Simpel: <script>, <style> raus, Tags strippen, Whitespace normalisieren
        if "html" in content_type.lower() or body.lstrip().startswith("<"):
            body = _strip_html(body)

        if len(body) > max_chars:
            body = body[:max_chars] + f"\n\n[…gekürzt, {len(body) - max_chars} weitere Zeichen folgten]"

        log.info("fetch_url: %s → %d chars", url, len(body))
        return f"URL: {url}\nContent-Type: {content_type}\n\n{body}"


def _strip_html(html: str) -> str:
    """Simple HTML-zu-Text-Conversion ohne BeautifulSoup-Dep."""
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;|&#160;", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&lt;", "<", html)
    html = re.sub(r"&gt;", ">", html)
    html = re.sub(r"&quot;", '"', html)
    html = re.sub(r"&#39;|&apos;", "'", html)
    html = re.sub(r"\s+\n", "\n", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    html = re.sub(r"[ \t]+", " ", html)
    return html.strip()
