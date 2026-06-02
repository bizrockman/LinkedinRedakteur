"""Playwright-basierter LinkedIn-Profil-Fetcher.

Architektur-Entscheidung — **Persistent Context statt storage_state**:
Wir nutzen `launch_persistent_context` mit einem dauerhaften User-Data-Dir
(`.playwright_linkedin_profile/`). Das ist ein vollständiger Browser-Profil-
Ordner, der zwischen Runs identisch bleibt — *inklusive* Cookies,
LocalStorage, IndexedDB UND Browser-Fingerprint.

Warum: `storage_state` (JSON mit Cookies) wechselt den Browser-Fingerprint
bei jedem Run. LinkedIn erkennt das als "andere Session mit denselben Cookies"
und zeigt eingeschränkte Inhalte (kein About, keine Posts). Persistent
Context fixt das, weil der Browser bei jedem Run identisch aussieht.

Stealth: Bewusst KEIN playwright-stealth — LinkedIn erkennt aggressive
Fingerprint-Manipulation als Bot. Mit einem echten Chrome-Profil + normalem
User-Agent erreichen wir bessere Ergebnisse.

Nutzung:
- Erster Aufruf: sichtbares Chromium öffnet sich, User loggt sich ein.
- Folgeläufe: Browser nutzt das gespeicherte Profil, kein Login mehr.
- Der `.playwright_linkedin_profile/` Ordner darf NICHT ins Git (gitignored).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from playwright.async_api import (
    BrowserContext,
    ElementHandle,
    Page,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PWTimeout,
)

from eve.core.entities import (
    AudienceDemographicEntry,
    AudienceDemographics,
    LinkedInPost,
    LinkedInProfileSnapshot,
)

PostsSource = Literal["recent", "top"]

log = logging.getLogger(__name__)

DEFAULT_SELECTORS_PATH = Path(__file__).parent / "selectors.yaml"
DEFAULT_USER_DATA_DIR = Path(".playwright_linkedin_profile")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _load_selectors(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class PlaywrightLinkedInFetcher:
    """LinkedIn-Scraping über einen echten Chromium-Browser mit Persistent Context.

    Args:
        user_data_dir: Ordner für das persistente Browser-Profil. Beim ersten
            Aufruf wird hier ein Chromium-Profil angelegt; nach dem manuellen
            Login bleibt es dauerhaft eingeloggt.
        headless: Browser headless laufen lassen. Für den ersten Login *muss*
            False sein. Danach kann True — aber LinkedIn erkennt headless-Mode
            zuverlässig, daher Default headed.
        login_timeout: Sekunden, die wir auf den manuellen Login warten.
        selectors_path: Optionaler Override-Pfad zur YAML mit Selektoren.
        use_real_chrome: Wenn True, wird der lokale Chrome statt Chromium
            verwendet (channel="chrome"). Reduziert Bot-Detection weiter.
    """

    source_name: str = "playwright"

    def __init__(
        self,
        user_data_dir: Path | str = DEFAULT_USER_DATA_DIR,
        *,
        headless: bool = False,
        login_timeout: int = 300,
        selectors_path: Path | str | None = None,
        use_real_chrome: bool = False,
        posts_source: PostsSource = "top",
    ) -> None:
        self.user_data_dir = Path(user_data_dir).resolve()
        self.headless = headless
        self.login_timeout = login_timeout
        self.use_real_chrome = use_real_chrome
        self.posts_source = posts_source
        self.selectors = _load_selectors(Path(selectors_path) if selectors_path else DEFAULT_SELECTORS_PATH)
        self._logged_in_patterns = [
            re.compile(p) for p in self.selectors["login"]["logged_in_url_patterns"]
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def fetch(
        self,
        profile_url: str,
        *,
        max_posts: int = 25,
    ) -> LinkedInProfileSnapshot:
        async with async_playwright() as pw:
            context = await self._launch_persistent(pw)
            try:
                await self._ensure_logged_in(context)
                page = await context.new_page()
                profile = await self._scrape_profile(page, profile_url)
                # Tolerate post-scrape failures; profile data is still valuable.
                try:
                    if self.posts_source == "top":
                        posts = await self._scrape_top_posts(page, max_posts=max_posts)
                    else:
                        posts = await self._scrape_posts(page, profile_url, max_posts=max_posts)
                except Exception as e:
                    log.warning("Posts scrape failed (%s); returning partial snapshot", e)
                    posts = []

                # Audience demographics — best-effort, kein Hard-Fail
                audience: AudienceDemographics | None = None
                try:
                    audience = await self._scrape_audience(page)
                except Exception as e:
                    log.warning("Audience scrape failed (%s); snapshot bleibt ohne Demographics", e)

                return LinkedInProfileSnapshot(
                    profile_url=profile_url,
                    name=profile.get("name", ""),
                    headline=profile.get("headline", ""),
                    about=profile.get("about", ""),
                    location=profile.get("location", ""),
                    posts=posts,
                    audience=audience,
                    scraped_at=datetime.now(),
                    raw=profile,
                )
            finally:
                await context.close()

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------
    async def _launch_persistent(self, pw) -> BrowserContext:
        """Persistent context — Browser-Profil bleibt zwischen Runs identisch."""
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        log.info("Using persistent profile at %s", self.user_data_dir)

        kwargs: dict = {
            "headless": self.headless,
            "user_agent": USER_AGENT,
            "viewport": {"width": 1366, "height": 900},
            "locale": "de-DE",
            "args": [
                "--disable-blink-features=AutomationControlled",
            ],
        }
        if self.use_real_chrome:
            kwargs["channel"] = "chrome"

        return await pw.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            **kwargs,
        )

    def _url_is_logged_in(self, url: str) -> bool:
        return any(p.match(url) for p in self._logged_in_patterns)

    async def _ensure_logged_in(self, context: BrowserContext) -> None:
        page = await context.new_page()
        login_url = self.selectors["login"]["login_url"]
        await page.goto(login_url, wait_until="domcontentloaded")

        # If already logged in, LinkedIn redirects away from /login within ~5s
        try:
            await page.wait_for_function(
                "() => !window.location.pathname.startsWith('/login')",
                timeout=5000,
            )
            if self._url_is_logged_in(page.url):
                log.info("Existing session valid.")
                await page.close()
                return
        except PWTimeout:
            pass

        if self.headless:
            raise RuntimeError(
                "No valid LinkedIn session and headless=True. "
                "Run once with headless=False to log in manually."
            )

        print(
            "\n>>> Bitte logge dich im geöffneten Browser-Fenster bei LinkedIn ein.\n"
            f"    Der Browser merkt sich den Login danach dauerhaft "
            f"({self.user_data_dir.name}).\n"
            f"    Warte bis zu {self.login_timeout}s auf erfolgreichen Login...\n"
        )
        try:
            await page.wait_for_function(
                "() => window.location.pathname.startsWith('/feed') "
                "|| window.location.pathname.startsWith('/in/')",
                timeout=self.login_timeout * 1000,
            )
            log.info("Login successful — profile is now persisted.")
        except PWTimeout as e:
            raise RuntimeError(
                "Login timeout — Browser-Fenster wurde nicht innerhalb der Frist erfolgreich erreicht"
            ) from e
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------
    async def _wait_for_ready(self, page: Page) -> None:
        for sel in self.selectors["page_ready"]:
            try:
                await page.wait_for_selector(sel, timeout=15000)
                return
            except PWTimeout:
                continue
        log.warning("page_ready selectors did not match")

    async def _scrape_profile(self, page: Page, profile_url: str) -> dict:
        await page.goto(profile_url, wait_until="domcontentloaded")
        await self._wait_for_ready(page)
        await asyncio.sleep(1.5)

        s = self.selectors["profile"]
        name = await self._first_text(page, s["name"])
        headline = await self._first_text(page, s["headline"])
        location = await self._first_text(page, s["location"])
        about = await self._extract_about(page, s["about_section"])

        return {
            "name": name or "",
            "headline": headline or "",
            "location": location or "",
            "about": about or "",
        }

    async def _scrape_posts(
        self,
        page: Page,
        profile_url: str,
        *,
        max_posts: int,
    ) -> list[LinkedInPost]:
        # LinkedIn redirects between several activity-URL variants. Try each.
        base = profile_url.rstrip("/")
        candidates = [
            f"{base}/recent-activity/all/",
            f"{base}/recent-activity/shares/",
            f"{base}/recent-activity/posts/",
            f"{base}/detail/recent-activity/shares/",
        ]
        landed = False
        for url in candidates:
            try:
                # `commit` resolves as soon as the navigation begins —
                # tolerates LinkedIn's intermediate redirects.
                await page.goto(url, wait_until="commit", timeout=20000)
                landed = True
                log.info("Activity URL accepted: %s → %s", url, page.url)
                break
            except Exception as e:
                log.warning("Activity URL failed (%s): %s", url, type(e).__name__)
                continue

        if not landed:
            log.warning("All activity URL variants failed; no posts will be scraped")
            return []

        # After commit, wait for the network to calm down a bit
        with contextlib.suppress(PWTimeout):
            await page.wait_for_load_state("networkidle", timeout=15000)
        try:
            await self._wait_for_ready(page)
        except PWTimeout:
            log.warning("Activity page main not visible after redirects")
            return []

        card_selectors = self.selectors["posts"]["card"]
        text_selectors = self.selectors["posts"]["text_within_card"]
        card_query = ", ".join(card_selectors)

        posts: list[LinkedInPost] = []
        seen_texts: set[str] = set()
        max_attempts = max_posts // 3 + 5

        for _ in range(max_attempts):
            if len(posts) >= max_posts:
                break
            cards = await page.query_selector_all(card_query)
            for card in cards:
                if len(posts) >= max_posts:
                    break
                text = await self._extract_post_text(card, text_selectors)
                if not text or text in seen_texts:
                    continue
                seen_texts.add(text)
                posts.append(LinkedInPost(text=text))

            await page.mouse.wheel(0, 5000)
            await asyncio.sleep(1.5)

        log.info("Scraped %d posts", len(posts))
        return posts

    async def _scrape_top_posts(
        self,
        page: Page,
        *,
        max_posts: int,
    ) -> list[LinkedInPost]:
        """Scrapt die nach Engagement sortierten Top-Performer aus dem
        Creator-Analytics-Dashboard. Diese Quelle liefert die *richtigen*
        Top-Performer (im Gegensatz zu /recent-activity/, das chronologisch ist).

        Funktioniert nur für das eigene Profil, da Analytics privat sind.
        """
        cfg = self.selectors["top_posts"]
        url = f"https://www.linkedin.com{cfg['url_path']}?{cfg['url_query']}"
        log.info("Navigating to top-posts analytics: %s", cfg["url_path"])
        await page.goto(url, wait_until="commit", timeout=20000)

        with contextlib.suppress(PWTimeout):
            await page.wait_for_load_state("networkidle", timeout=20000)
        try:
            await self._wait_for_ready(page)
        except PWTimeout:
            log.warning("Top-posts page not ready")
            return []

        # Final URL check — falls LinkedIn auf Login redirected hat
        if "/login" in page.url or "/authwall" in page.url:
            log.warning("Top-posts redirected to login; user not authenticated for analytics")
            return []

        await asyncio.sleep(1.5)

        card_selectors = cfg["card"]
        text_selectors = cfg["text_within_card"]
        engagement_selectors = cfg["engagement_within_card"]
        byline_re = re.compile(cfg["byline_regex"])

        card_query = ", ".join(card_selectors)
        cards = await page.query_selector_all(card_query)
        log.info("Top-posts cards found: %d", len(cards))

        posts: list[LinkedInPost] = []
        for card in cards[:max_posts]:
            text = await self._extract_post_text(card, text_selectors)
            if not text:
                continue
            # Byline-Vorspann ("Danny Gerst hat dies gepostet • 3 Monate") strippen
            cleaned = byline_re.sub("", text, count=1).strip()
            if len(cleaned) < 50:
                continue

            engagement = await self._extract_engagement(card, engagement_selectors)
            posts.append(
                LinkedInPost(
                    text=cleaned,
                    likes=engagement.get("engagement"),  # "Engagement"-Zahl als grobe Approximation
                )
            )

        log.info("Scraped %d top-performer posts", len(posts))
        return posts

    async def _scrape_audience(self, page: Page) -> AudienceDemographics | None:
        """Scrapt Audience-Demographics aus dem Creator-Analytics-Dashboard.

        Liefert i.d.R. 5-6 Kategorien (Jobbezeichnung, Standort, Branche,
        Karrierestufe, Firmengröße, ggf. Berufserfahrung) — jede mit Top-5.

        Funktioniert nur für das eigene Profil (Analytics sind privat).
        """
        cfg = self.selectors["audience"]
        url = f"https://www.linkedin.com{cfg['url_path']}?{cfg['url_query']}"
        log.info("Navigating to audience demographics: %s", cfg["url_path"])
        await page.goto(url, wait_until="commit", timeout=20000)

        with contextlib.suppress(PWTimeout):
            await page.wait_for_load_state("networkidle", timeout=20000)
        try:
            await self._wait_for_ready(page)
        except PWTimeout:
            log.warning("Audience page not ready")
            return None

        if "/login" in page.url or "/authwall" in page.url:
            log.warning("Audience redirected to login; analytics not accessible")
            return None

        await asyncio.sleep(1.5)

        chart_query = ", ".join(cfg["chart"])
        charts = await page.query_selector_all(chart_query)
        log.info("Audience demographic charts found: %d", len(charts))

        categories: dict[str, list[AudienceDemographicEntry]] = {}
        for chart in charts:
            heading = await self._first_text_within(chart, cfg["chart_heading"])
            if not heading:
                continue
            rows_query = ", ".join(cfg["chart_row"])
            row_elements = await chart.query_selector_all(rows_query)

            entries: list[AudienceDemographicEntry] = []
            for row in row_elements:
                label = await self._first_text_within(row, cfg["row_label"])
                pct = await self._first_text_within(row, cfg["row_percentage"])
                if label and pct:
                    entries.append(AudienceDemographicEntry(label=label, percentage=pct))

            if entries:
                categories[heading] = entries

        if not categories:
            return None
        return AudienceDemographics(categories=categories)

    @staticmethod
    async def _first_text_within(element: ElementHandle, selectors: list[str]) -> str | None:
        """Findet den ersten Text innerhalb eines Elements (statt einer Page)."""
        for sel in selectors:
            try:
                child = await element.query_selector(sel)
                if child:
                    txt = (await child.inner_text()).strip()
                    if txt:
                        return txt
            except Exception:
                continue
        return None

    @staticmethod
    async def _extract_engagement(card: ElementHandle, selectors: list[str]) -> dict[str, int]:
        """Versucht die Engagement-Zahl aus dem Footer einer Top-Post-Card zu parsen."""
        for sel in selectors:
            try:
                el = await card.query_selector(sel)
                if el:
                    text = (await el.inner_text()).strip()
                    # Format ist typischerweise "335\nEngagement" oder " 335 / Engagement"
                    match = re.search(r"(\d[\d.,]*)", text)
                    if match:
                        raw = match.group(1).replace(".", "").replace(",", "")
                        with contextlib.suppress(ValueError):
                            return {"engagement": int(raw)}
            except Exception:
                continue
        return {}

    # ------------------------------------------------------------------
    # Selector helpers
    # ------------------------------------------------------------------
    @staticmethod
    async def _first_text(page: Page, selectors: list[str]) -> str | None:
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    txt = (await el.inner_text()).strip()
                    if txt:
                        return txt
            except Exception:
                continue
        return None

    @staticmethod
    async def _extract_post_text(card: ElementHandle, selectors: list[str]) -> str | None:
        for sel in selectors:
            try:
                el = await card.query_selector(sel)
                if el:
                    text = (await el.inner_text()).strip()
                    if text and len(text) > 20:
                        return text
            except Exception:
                continue
        return None

    @staticmethod
    async def _extract_about(page: Page, selectors: list[str]) -> str:
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    raw = (await el.inner_text()).strip()
                    # Strip the section heading itself ("Info" / "About")
                    cleaned = re.sub(r"^(Info|About)\s*\n", "", raw, flags=re.IGNORECASE)
                    if cleaned:
                        return cleaned
            except Exception:
                continue
        return ""


def dump_snapshot_to_json(snapshot: LinkedInProfileSnapshot, out: Path) -> None:
    """Hilfsfunktion zum lokalen Wegspeichern eines Snapshots als JSON."""
    out.write_text(
        json.dumps(snapshot.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
