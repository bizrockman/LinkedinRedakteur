"""Posts-Tools — CRUD-Operationen via PostsRepository.

Verwendet PostsRepository-Port — Container entscheidet ob Filesystem-Sidecar
oder Supabase. Tools sind agnostisch.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from eve.agent.tools.base import ToolDefinition
from eve.core.entities import PostSource, PostStatus, StoredPost
from eve.core.ports import PostsRepository

log = logging.getLogger(__name__)


class SearchPostsTool:
    """Sucht in den gespeicherten Posts (für Dedup, Stilreferenz, Coverage-Check)."""

    def __init__(self, repo: PostsRepository, profile_id: str) -> None:
        self.repo = repo
        self.profile_id = profile_id

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_posts",
            description=(
                "Durchsucht die gespeicherten Posts (Editorial Plan + Historie). "
                "Nutze dies vor jedem neuen Post-Vorschlag, um Wiederholungen "
                "zu vermeiden ('Hatte ich das Thema schon?') und um den Stil "
                "vergangener erfolgreicher Posts zu studieren."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Suchbegriff im Post-Text (case-insensitive substring). Leer = alle.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["draft", "ready", "posted", "error", "archived"],
                        "description": "Optional Status-Filter.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max Anzahl Ergebnisse (default 10)",
                    },
                },
                "required": [],
            },
        )

    async def execute(self, args: dict[str, Any]) -> str:
        query = args.get("query") or None
        status_str = args.get("status")
        status = PostStatus(status_str) if status_str else None
        limit = int(args.get("limit", 10))

        matches = await self.repo.search(
            profile_id=self.profile_id,
            query=query,
            status=status,
            limit=limit,
        )

        if not matches:
            return f"Keine Posts gefunden (query={query!r}, status={status})."

        lines = [f"Gefunden: {len(matches)} Posts:"]
        for i, p in enumerate(matches, 1):
            preview = p.text[:200].replace("\n", " ")
            date_str = p.posted_at.strftime("%Y-%m-%d") if p.posted_at else "n/a"
            lines.append(
                f"\n[{i}] id={p.id} status={p.status} source={p.source} posted={date_str}\n"
                f"    {preview}{'…' if len(p.text) > 200 else ''}"
            )
        return "\n".join(lines)


class CreatePostTool:
    """Legt einen neuen Post-Draft an."""

    def __init__(self, repo: PostsRepository, profile_id: str) -> None:
        self.repo = repo
        self.profile_id = profile_id

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="create_post",
            description=(
                "Erstellt einen neuen Post im Editorial Plan. Status ist standardmäßig "
                "'draft' — der User muss anschließend manuell freigeben, bevor er "
                "zum 'ready'-Status wechselt und automatisch gepostet wird. "
                "Setze scheduled_for auf das gewünschte Posting-Datum (ISO 8601)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Vollständiger Post-Text"},
                    "scheduled_for": {
                        "type": "string",
                        "description": "ISO-8601 Datum/Zeit (z.B. '2026-06-15T09:00:00') — wann gepostet werden soll",
                    },
                    "creative_url": {
                        "type": "string",
                        "description": "Optional URL zum begleitenden Bild (idealerweise Supabase-Storage-URL nach generate_image)",
                    },
                    "creative_prompt": {
                        "type": "string",
                        "description": "Optional der Prompt mit dem das Bild generiert wurde (für Re-Generieren)",
                    },
                },
                "required": ["text"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> str:
        text = args.get("text", "").strip()
        if not text:
            return "Fehler: text ist leer."

        scheduled_for_raw = args.get("scheduled_for")
        scheduled_for = None
        if scheduled_for_raw:
            try:
                scheduled_for = datetime.fromisoformat(scheduled_for_raw)
            except ValueError:
                return f"Fehler: ungültiges Datum-Format '{scheduled_for_raw}'. Erwartet ISO 8601."

        metadata: dict[str, Any] = {}
        if creative_prompt := args.get("creative_prompt"):
            metadata["creative_prompt"] = creative_prompt

        post = StoredPost(
            profile_id=self.profile_id,
            text=text,
            status=PostStatus.DRAFT,
            source=PostSource.EVE,
            scheduled_for=scheduled_for,
            creative_url=args.get("creative_url"),
            metadata=metadata,
        )

        created = await self.repo.create(post)
        log.info("Created post id=%s for profile=%s", created.id, self.profile_id)
        return (
            f"✓ Post angelegt:\n"
            f"  id:            {created.id}\n"
            f"  status:        {created.status.value}\n"
            f"  scheduled_for: {scheduled_for.isoformat() if scheduled_for else 'nicht gesetzt'}\n"
            f"  creative_url:  {created.creative_url or '—'}"
        )


class UpdatePostTool:
    """Updated einen existierenden Post (Status, Datum, Text)."""

    def __init__(self, repo: PostsRepository, profile_id: str) -> None:
        self.repo = repo
        self.profile_id = profile_id

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="update_post",
            description=(
                "Updated einen existierenden Post. Nur die übergebenen Felder werden "
                "geändert. Häufigster Use Case: status von 'draft' auf 'ready' setzen, "
                "wenn der User freigegeben hat."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID des Posts"},
                    "text": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["draft", "ready", "posted", "error", "archived"],
                    },
                    "scheduled_for": {"type": "string", "description": "ISO 8601"},
                    "creative_url": {"type": "string"},
                },
                "required": ["id"],
            },
        )

    async def execute(self, args: dict[str, Any]) -> str:
        post_id_str = args.get("id", "").strip()
        try:
            post_id = UUID(post_id_str)
        except ValueError:
            return f"Fehler: ungültige UUID '{post_id_str}'"

        target = await self.repo.get(post_id)
        if target is None or target.profile_id != self.profile_id:
            return f"Post mit id={post_id} nicht gefunden."

        if (text := args.get("text")) is not None:
            target.text = text
        if (status := args.get("status")) is not None:
            target.status = PostStatus(status)
        if (sf := args.get("scheduled_for")) is not None:
            try:
                target.scheduled_for = datetime.fromisoformat(sf)
            except ValueError:
                return f"Fehler: ungültiges Datum '{sf}'"
        if (cu := args.get("creative_url")) is not None:
            target.creative_url = cu

        updated = await self.repo.update(target)
        return f"✓ Post id={post_id} aktualisiert. status={updated.status.value}"
