"""GDPR-Export-basierter LinkedIn-Fetcher.

LinkedIn-Nutzer können unter
    https://www.linkedin.com/mypreferences/d/download-my-data
einen vollständigen Datenexport anfordern. Die ZIP enthält u.a.:
    Profile.csv  — Stammdaten (Name, Headline, Summary, ...)
    Shares.csv   — ALLE veröffentlichten Posts (Date, ShareCommentary, ...)
    Articles.csv — Langform-Beiträge (optional)

Dieser Adapter:
- akzeptiert entweder eine ZIP-Datei oder ein bereits entpacktes Verzeichnis
- 100% offline & ohne Browser-Automation → kein Bot-Detection-Risiko
- liefert dieselbe `LinkedInProfileSnapshot` wie der Playwright-Adapter

Vorteil ggü. Scraping: vollständige Posts-Historie (nicht nur die letzten 25).
Nachteil: User muss 24h auf den Export warten.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

from eve.core.entities import LinkedInPost, LinkedInProfileSnapshot

log = logging.getLogger(__name__)

# Wir suchen diese Dateien case-insensitive irgendwo im Export
PROFILE_FILENAMES = {"profile.csv"}
SHARES_FILENAMES = {"shares.csv"}
ARTICLES_FILENAMES = {"articles.csv"}

# LinkedIn Basic-Export liefert Artikel als HTML in Articles/Articles/*.html
HTML_ARTICLE_PATTERN = re.compile(r".*Articles[/\\]Articles[/\\].*\.html$", re.IGNORECASE)


class GdprExportLinkedInFetcher:
    """Parsed einen LinkedIn-Datenexport (ZIP oder Verzeichnis).

    Args:
        export_path: Pfad zur ZIP oder zum entpackten Export-Ordner.
        include_articles: Wenn True, werden auch Long-Form-Artikel als Posts
            mitgenommen.
    """

    source_name: str = "gdpr-export"

    def __init__(
        self,
        export_path: Path | str,
        *,
        include_articles: bool = False,
    ) -> None:
        self.export_path = Path(export_path)
        if not self.export_path.exists():
            raise FileNotFoundError(f"Export path not found: {self.export_path}")
        self.include_articles = include_articles

    async def fetch(
        self,
        profile_url: str = "",
        *,
        max_posts: int = 25,
    ) -> LinkedInProfileSnapshot:
        """Liest Profil- und Posts-Daten aus dem Export.

        Args:
            profile_url: Optional — nur zur Speicherung im Snapshot.
                LinkedIn legt die URL nicht zwingend in der Profile.csv ab.
            max_posts: Maximalanzahl der zurückgegebenen Posts
                (chronologisch neueste zuerst).
        """
        files, html_articles = self._index_files()

        profile_data = self._read_profile(files)
        posts = self._read_shares(files)
        if self.include_articles:
            posts.extend(self._read_articles(files))
            posts.extend(self._read_html_articles(html_articles))

        # Neueste zuerst, dann begrenzen
        posts.sort(key=lambda p: p.posted_at or datetime.min, reverse=True)
        posts = posts[:max_posts]

        return LinkedInProfileSnapshot(
            profile_url=profile_url or profile_data.get("profile_url", ""),
            name=profile_data.get("name", ""),
            headline=profile_data.get("headline", ""),
            about=profile_data.get("about", ""),
            location=profile_data.get("location", ""),
            posts=posts,
            scraped_at=datetime.now(),
            raw={"source": "gdpr-export", "profile_csv": profile_data},
        )

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------
    def _index_files(self) -> tuple[dict[str, bytes], dict[str, bytes]]:
        """Sammelt alle relevanten Dateien.

        Returns:
            Tupel (csv_files, html_articles):
                csv_files: {lowercased_name → bytes} für Profile/Shares/Articles CSV
                html_articles: {relative_path → bytes} für HTML-Artikel
        """
        wanted = PROFILE_FILENAMES | SHARES_FILENAMES | ARTICLES_FILENAMES
        csv_out: dict[str, bytes] = {}
        html_out: dict[str, bytes] = {}

        if self.export_path.is_file() and self.export_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(self.export_path) as zf:
                for info in zf.infolist():
                    name = Path(info.filename).name.lower()
                    if name in wanted:
                        csv_out[name] = zf.read(info.filename)
                    elif HTML_ARTICLE_PATTERN.match(info.filename):
                        html_out[info.filename] = zf.read(info.filename)
        elif self.export_path.is_dir():
            for p in self.export_path.rglob("*"):
                if not p.is_file():
                    continue
                if p.name.lower() in wanted:
                    csv_out[p.name.lower()] = p.read_bytes()
                elif HTML_ARTICLE_PATTERN.match(str(p)):
                    html_out[str(p.relative_to(self.export_path))] = p.read_bytes()
        else:
            raise ValueError(
                f"Export path must be a .zip or a directory: {self.export_path}"
            )

        log.info(
            "Found %d CSV files and %d HTML articles",
            len(csv_out),
            len(html_out),
        )
        return csv_out, html_out

    # ------------------------------------------------------------------
    # Profile.csv
    # ------------------------------------------------------------------
    def _read_profile(self, files: dict[str, bytes]) -> dict[str, str]:
        for fname in PROFILE_FILENAMES:
            if fname in files:
                rows = list(self._csv_rows(files[fname]))
                if not rows:
                    return {}
                row = rows[0]  # Profile.csv has exactly one data row
                first = (row.get("First Name") or "").strip()
                last = (row.get("Last Name") or "").strip()
                full_name = f"{first} {last}".strip()
                return {
                    "name": full_name,
                    "headline": (row.get("Headline") or "").strip(),
                    "about": (row.get("Summary") or "").strip(),
                    "location": (row.get("Geo Location") or "").strip(),
                    "industry": (row.get("Industry") or "").strip(),
                }
        log.warning("Profile.csv not found in export")
        return {}

    # ------------------------------------------------------------------
    # Shares.csv
    # ------------------------------------------------------------------
    def _read_shares(self, files: dict[str, bytes]) -> list[LinkedInPost]:
        for fname in SHARES_FILENAMES:
            if fname in files:
                return [
                    LinkedInPost(
                        text=(row.get("ShareCommentary") or "").strip(),
                        url=(row.get("ShareLink") or "").strip() or None,
                        posted_at=self._parse_date(row.get("Date") or ""),
                        media_urls=self._split_media(row.get("MediaUrl") or ""),
                    )
                    for row in self._csv_rows(files[fname])
                    if (row.get("ShareCommentary") or "").strip()
                ]
        log.warning("Shares.csv not found in export")
        return []

    def _read_html_articles(self, files: dict[str, bytes]) -> list[LinkedInPost]:
        """Parses LinkedIn Long-Form-Artikel aus Articles/Articles/*.html.

        Im Basic-Export liefert LinkedIn die Artikel als gerendertes HTML
        (kein Markdown, keine CSV). Wir extrahieren Title, Created-Date,
        und den reinen Paragraph-Text.
        """
        posts: list[LinkedInPost] = []
        for name, data in files.items():
            try:
                html = data.decode("utf-8", errors="replace")
                article = _parse_linkedin_article_html(html)
                if article["body"]:
                    title = article["title"].strip()
                    body = article["body"].strip()
                    text = f"{title}\n\n{body}" if title else body
                    posts.append(
                        LinkedInPost(
                            text=text,
                            posted_at=self._parse_date(article["created"]),
                        )
                    )
            except Exception as e:
                log.warning("Failed to parse HTML article %s: %s", name, e)
        log.info("Parsed %d HTML articles", len(posts))
        return posts

    def _read_articles(self, files: dict[str, bytes]) -> list[LinkedInPost]:
        for fname in ARTICLES_FILENAMES:
            if fname in files:
                return [
                    LinkedInPost(
                        text=self._compose_article_text(row),
                        url=(row.get("ArticleLink") or "").strip() or None,
                        posted_at=self._parse_date(row.get("Date") or ""),
                    )
                    for row in self._csv_rows(files[fname])
                    if (row.get("ArticleTitle") or "").strip()
                ]
        return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _csv_rows(data: bytes):
        # LinkedIn exports sind UTF-8 mit BOM
        text = data.decode("utf-8-sig", errors="replace")
        yield from csv.DictReader(io.StringIO(text))

    @staticmethod
    def _parse_date(value: str) -> datetime | None:
        if not value:
            return None
        value = value.strip()
        # Beobachtete Formate
        formats = [
            "%Y-%m-%d %H:%M:%S UTC",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",           # LinkedIn HTML-Artikel: "Created on YYYY-MM-DD HH:MM"
            "%Y-%m-%d",
            "%m/%d/%Y %H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        log.debug("Could not parse date '%s'", value)
        return None

    @staticmethod
    def _split_media(value: str) -> list[str]:
        if not value.strip():
            return []
        return [u.strip() for u in value.split(",") if u.strip()]

    @staticmethod
    def _compose_article_text(row: dict[str, str]) -> str:
        title = (row.get("ArticleTitle") or "").strip()
        body = (row.get("Content") or row.get("ArticleContent") or "").strip()
        if title and body:
            return f"{title}\n\n{body}"
        return title or body


class _LinkedInArticleHTMLParser(HTMLParser):
    """Extracts title, created-date and paragraph text from a LinkedIn article HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str = ""
        self.created: str = ""
        self._buf: list[str] = []
        self._collect_into: str | None = None
        # Track <p class="created"> specifically
        self._in_created_p = False
        # Track if we are inside the body <div> after the metadata
        self._after_meta = False
        # Track if we are inside <h1>
        self._in_h1 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h1" and not self.title:
            self._in_h1 = True
            self._collect_into = "title"
            return
        if tag == "p":
            cls = next((v for k, v in attrs if k == "class"), "") or ""
            if "created" in cls:
                self._in_created_p = True
                self._collect_into = "created"
                return
            if "published" in cls:
                # ignore the "Published on ---" line — it's metadata, not content
                self._collect_into = None
                return
            if self._after_meta:
                # Regular paragraph in body
                self._collect_into = "body"
                return
        elif tag == "div" and not self._after_meta:
            # The body <div> sits right after the <p class="published"> line
            self._after_meta = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1" and self._in_h1:
            self.title = "".join(self._buf).strip()
            self._buf = []
            self._in_h1 = False
            self._collect_into = None
        elif tag == "p" and self._in_created_p:
            text = "".join(self._buf).strip()
            # "Created on 2026-02-14 22:34" → strip prefix
            self.created = re.sub(r"^Created on\s*", "", text, flags=re.IGNORECASE).strip()
            self._buf = []
            self._in_created_p = False
            self._collect_into = None
        elif tag == "p" and self._collect_into == "body":
            paragraph = "".join(self._buf).strip()
            if paragraph:
                # Use a sentinel separator we replace at the end
                self._paragraphs.append(paragraph)
            self._buf = []
            self._collect_into = None

    def handle_data(self, data: str) -> None:
        if self._collect_into is not None:
            self._buf.append(data)

    @property
    def _paragraphs(self) -> list[str]:
        if not hasattr(self, "_p_list"):
            self._p_list: list[str] = []
        return self._p_list

    @property
    def body(self) -> str:
        return "\n\n".join(self._paragraphs)


def _parse_linkedin_article_html(html: str) -> dict[str, str]:
    """Pure-stdlib HTML extraction for LinkedIn-exported article HTMLs.

    Returns dict with keys: title, created, body.
    """
    parser = _LinkedInArticleHTMLParser()
    # Strip <style> blocks first — they contain noisy text
    cleaned = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    parser.feed(cleaned)
    return {
        "title": parser.title,
        "created": parser.created,
        "body": parser.body,
    }
