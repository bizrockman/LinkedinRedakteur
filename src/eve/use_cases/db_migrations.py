"""Migration-Discovery für das `eve`-Schema.

In der vereinfachten Supabase-Architektur (nur supabase-py, kein asyncpg)
werden Migrations *manuell* via Dashboard SQL Editor angewendet. Dieses
Modul liefert die Building-Blocks dafür:

- `discover_migrations()` findet alle SQL-Files in /migrations
- `MigrationFile` enthält Name + Inhalt + SHA-256
- `dashboard_sql_editor_url(ref)` baut den Deep-Link zum SQL-Editor

Die eigentliche Anwendung passiert per Copy-Paste durch den User. Für
Production / CI lohnt sich später die Supabase CLI (`supabase db push`).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MIGRATIONS_DIR = Path("migrations")


@dataclass(frozen=True)
class MigrationFile:
    filename: str
    path: Path
    sha256: str
    content: str

    @classmethod
    def load(cls, path: Path) -> MigrationFile:
        content = path.read_text(encoding="utf-8")
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return cls(filename=path.name, path=path, sha256=sha, content=content)


MAIN_SQL_FILE = "main.sql"


def discover_migrations(migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[MigrationFile]:
    """Findet das `main.sql` Setup-File (idempotent, eine Datei für den User).

    Die nummerierten Migrations (0001_, 0002_) bleiben als History im
    Repo, werden aber nicht standardmäßig zurückgegeben. Wer sie explicit
    braucht, kann `discover_all_migrations()` nutzen.
    """
    if not migrations_dir.exists():
        return []
    main = migrations_dir / MAIN_SQL_FILE
    if not main.exists():
        # Fallback: alle nummerierten Files
        return [MigrationFile.load(p) for p in sorted(migrations_dir.glob("*.sql"))]
    return [MigrationFile.load(main)]


def discover_all_migrations(
    migrations_dir: Path = DEFAULT_MIGRATIONS_DIR,
) -> list[MigrationFile]:
    """Alle .sql Files inkl. nummerierten History (für Audit / Manual-Reapply)."""
    if not migrations_dir.exists():
        return []
    return [MigrationFile.load(p) for p in sorted(migrations_dir.glob("*.sql"))]


def dashboard_sql_editor_url(project_ref: str) -> str:
    """Deep-Link in den Supabase-Dashboard SQL Editor."""
    return f"https://supabase.com/dashboard/project/{project_ref}/sql/new"
