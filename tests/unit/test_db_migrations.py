"""Tests für Migration-Discovery + Dashboard-Link-Bau."""

from __future__ import annotations

import tempfile
from pathlib import Path

from eve.use_cases.db_migrations import (
    MigrationFile,
    dashboard_sql_editor_url,
    discover_all_migrations,
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


def test_discover_prefers_main_sql_when_present():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        (d / "0001_a.sql").write_text("SELECT 1;", encoding="utf-8")
        (d / "0002_b.sql").write_text("SELECT 2;", encoding="utf-8")
        (d / "main.sql").write_text("SELECT 'main';", encoding="utf-8")

        # discover_migrations zeigt NUR main.sql
        only_main = discover_migrations(d)
        assert len(only_main) == 1
        assert only_main[0].filename == "main.sql"

        # discover_all_migrations zeigt alle (für History/Audit)
        all_files = discover_all_migrations(d)
        assert [f.filename for f in all_files] == ["0001_a.sql", "0002_b.sql", "main.sql"]


def test_discover_falls_back_when_no_main_sql():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        (d / "0001_a.sql").write_text("SELECT 1;", encoding="utf-8")
        (d / "0002_b.sql").write_text("SELECT 2;", encoding="utf-8")
        # Kein main.sql → fällt auf nummerierte zurück
        files = discover_migrations(d)
        assert [f.filename for f in files] == ["0001_a.sql", "0002_b.sql"]
