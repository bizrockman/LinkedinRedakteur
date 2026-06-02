"""Tests für Migration-Discovery + Dashboard-Link-Bau."""

from __future__ import annotations

import tempfile
from pathlib import Path

from eve.use_cases.db_migrations import (
    MigrationFile,
    dashboard_sql_editor_url,
    discover_migrations,
)


def test_discover_empty_dir():
    with tempfile.TemporaryDirectory() as t:
        assert discover_migrations(Path(t)) == []


def test_discover_returns_sorted():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        (d / "0002_b.sql").write_text("SELECT 2;", encoding="utf-8")
        (d / "0001_a.sql").write_text("SELECT 1;", encoding="utf-8")
        (d / "0003_c.sql").write_text("SELECT 3;", encoding="utf-8")
        files = discover_migrations(d)
        assert [f.filename for f in files] == ["0001_a.sql", "0002_b.sql", "0003_c.sql"]


def test_migration_file_loads_content_and_hash():
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "x.sql"
        path.write_text("SELECT 'hello';", encoding="utf-8")
        mig = MigrationFile.load(path)
        assert mig.filename == "x.sql"
        assert mig.content == "SELECT 'hello';"
        assert len(mig.sha256) == 64


def test_dashboard_url():
    assert dashboard_sql_editor_url("abc123xyz") == (
        "https://supabase.com/dashboard/project/abc123xyz/sql/new"
    )
