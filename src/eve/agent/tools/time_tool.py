"""now-Tool — gibt aktuelle Uhrzeit + Datum zurück.

Auch wenn das Datum schon im System-Prompt steht, ist ein Tool hilfreich für:
- Datums-Arithmetik ("Wann ist nächster Montag?")
- Mehrfache Abfragen in einer Konversation
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from eve.agent.tools.base import ToolDefinition


class NowTool:
    """Liefert die aktuelle Zeit in mehreren Formaten."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="now",
            description=(
                "Liefert die aktuelle Uhrzeit, das Datum, den Wochentag und die "
                "Kalenderwoche. Nutze dieses Tool, wenn du eine zeitliche "
                "Berechnung machst (z.B. 'in 3 Tagen', 'nächster Montag') oder "
                "wenn du sicherstellen willst, dass du die aktuellste Zeit hast."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Optional: IANA-Timezone (z.B. 'Europe/Berlin'). Default: UTC.",
                    }
                },
                "required": [],
            },
        )

    async def execute(self, args: dict[str, Any]) -> str:
        tz_name = args.get("timezone", "UTC")
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(tz_name) if tz_name != "UTC" else None
            now = datetime.now(tz) if tz else datetime.utcnow()
        except Exception:
            now = datetime.utcnow()
            tz_name = "UTC (fallback)"

        weekday_de = [
            "Montag", "Dienstag", "Mittwoch", "Donnerstag",
            "Freitag", "Samstag", "Sonntag",
        ][now.weekday()]

        return (
            f"Aktuelle Zeit ({tz_name}):\n"
            f"  ISO:        {now.isoformat()}\n"
            f"  Wochentag:  {weekday_de}\n"
            f"  KW:         {now.isocalendar().week}\n"
            f"  Datum:      {now.strftime('%d.%m.%Y')}\n"
            f"  Uhrzeit:    {now.strftime('%H:%M')}"
        )
