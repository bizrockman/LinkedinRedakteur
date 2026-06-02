"""Tests für GdprExportLinkedInFetcher mit synthetischen LinkedIn-Exports."""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import pytest

from eve.adapters.linkedin.gdpr_export_fetcher import GdprExportLinkedInFetcher

PROFILE_CSV = (
    "First Name,Last Name,Headline,Summary,Industry,Geo Location\r\n"
    "Dominic,Müller,LinkedIn Strategist | KI-Adoption,"
    '"Ich helfe Mittelständlern, KI sinnvoll einzusetzen.",'
    "Information Technology,Berlin, Germany\r\n"
)

SHARES_CSV = (
    "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl,MediaType,Visibility\r\n"
    "2026-05-01 10:00:00 UTC,https://linkedin.com/feed/update/1,"
    '"Erster Post-Text mit Inhalt.",,,NONE,PUBLIC\r\n'
    "2026-05-10 12:30:00 UTC,https://linkedin.com/feed/update/2,"
    '"Zweiter Post mit etwas mehr Substanz im Text.",,'
    'https://media.linkedin.com/img1.png,IMAGE,PUBLIC\r\n'
    '2026-05-15 09:00:00 UTC,https://linkedin.com/feed/update/3,"",,,NONE,PUBLIC\r\n'  # empty commentary, should be skipped
)


def _make_zip_export(tmp_dir: Path) -> Path:
    """Schreibt einen ZIP-Export mit Profile.csv + Shares.csv."""
    zip_path = tmp_dir / "export.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Profile.csv", PROFILE_CSV.encode("utf-8-sig"))
        zf.writestr("Shares.csv", SHARES_CSV.encode("utf-8-sig"))
    zip_path.write_bytes(buf.getvalue())
    return zip_path


def _make_dir_export(tmp_dir: Path) -> Path:
    """Schreibt einen entpackten Export."""
    d = tmp_dir / "extracted"
    d.mkdir()
    (d / "Profile.csv").write_bytes(PROFILE_CSV.encode("utf-8-sig"))
    (d / "Shares.csv").write_bytes(SHARES_CSV.encode("utf-8-sig"))
    return d


@pytest.fixture
def tmp_export_zip():
    with tempfile.TemporaryDirectory() as t:
        yield _make_zip_export(Path(t))


@pytest.fixture
def tmp_export_dir():
    with tempfile.TemporaryDirectory() as t:
        yield _make_dir_export(Path(t))


async def test_fetch_from_zip(tmp_export_zip: Path):
    fetcher = GdprExportLinkedInFetcher(tmp_export_zip)
    snap = await fetcher.fetch(profile_url="https://linkedin.com/in/dominic/")

    assert snap.name == "Dominic Müller"
    assert "KI-Adoption" in snap.headline
    assert "Mittelständlern" in snap.about
    assert "Berlin" in snap.location
    # Empty-commentary row is filtered out
    assert len(snap.posts) == 2
    # Sorted newest first
    assert "Zweiter Post" in snap.posts[0].text
    assert "Erster Post" in snap.posts[1].text


async def test_fetch_from_directory(tmp_export_dir: Path):
    fetcher = GdprExportLinkedInFetcher(tmp_export_dir)
    snap = await fetcher.fetch()
    assert snap.name == "Dominic Müller"
    assert len(snap.posts) == 2


async def test_fetch_respects_max_posts(tmp_export_zip: Path):
    fetcher = GdprExportLinkedInFetcher(tmp_export_zip)
    snap = await fetcher.fetch(max_posts=1)
    assert len(snap.posts) == 1
    assert "Zweiter Post" in snap.posts[0].text  # newest first


async def test_missing_export_raises():
    with pytest.raises(FileNotFoundError):
        GdprExportLinkedInFetcher("nonexistent.zip")


async def test_source_name_constant():
    with tempfile.TemporaryDirectory() as t:
        zp = _make_zip_export(Path(t))
        assert GdprExportLinkedInFetcher(zp).source_name == "gdpr-export"


async def test_dates_parsed(tmp_export_zip: Path):
    fetcher = GdprExportLinkedInFetcher(tmp_export_zip)
    snap = await fetcher.fetch()
    assert snap.posts[0].posted_at is not None
    assert snap.posts[0].posted_at.year == 2026
    assert snap.posts[0].posted_at.month == 5


async def test_media_urls_extracted(tmp_export_zip: Path):
    fetcher = GdprExportLinkedInFetcher(tmp_export_zip)
    snap = await fetcher.fetch()
    # The newest post (Zweiter Post) has a media URL
    assert snap.posts[0].media_urls == ["https://media.linkedin.com/img1.png"]
    assert snap.posts[1].media_urls == []


# --- HTML article parsing -------------------------------------------------

ARTICLE_HTML = """<html>
<head><title>Mein Test-Artikel</title>
<style>body { color: red; }</style>
</head>
<body>
<img src="https://x.com/banner.jpg" />
<h1>Mein Test-Artikel über KI</h1>
<p class="created">Created on 2026-03-15 10:30</p>
<p class="published">Published on ---</p>
<div>
<p>Erster Absatz mit etwas Inhalt zum Thema KI im Mittelstand.</p>
<p>Zweiter Absatz mit Details und Strukturen.</p>
<p>Dritter Absatz zum Abschluss.</p>
</div>
</body>
</html>"""


def _make_html_export(tmp_dir: Path) -> Path:
    """Schreibt einen Export mit Profile.csv + einem HTML-Artikel."""
    zip_path = tmp_dir / "html_export.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Profile.csv", PROFILE_CSV.encode("utf-8-sig"))
        zf.writestr(
            "Articles/Articles/2026-03-15 10:30:00.0-Mein-Artikel.html",
            ARTICLE_HTML.encode("utf-8"),
        )
    zip_path.write_bytes(buf.getvalue())
    return zip_path


@pytest.fixture
def tmp_html_export():
    with tempfile.TemporaryDirectory() as t:
        yield _make_html_export(Path(t))


async def test_html_article_parsed_when_include_articles(tmp_html_export: Path):
    fetcher = GdprExportLinkedInFetcher(tmp_html_export, include_articles=True)
    snap = await fetcher.fetch()
    assert len(snap.posts) == 1
    post = snap.posts[0]
    assert "Mein Test-Artikel über KI" in post.text
    assert "Erster Absatz" in post.text
    assert "Dritter Absatz" in post.text
    # Style block content must not leak in
    assert "color: red" not in post.text
    assert post.posted_at is not None
    assert post.posted_at.year == 2026
    assert post.posted_at.month == 3


async def test_html_article_skipped_without_include_articles(tmp_html_export: Path):
    fetcher = GdprExportLinkedInFetcher(tmp_html_export, include_articles=False)
    snap = await fetcher.fetch()
    assert len(snap.posts) == 0
