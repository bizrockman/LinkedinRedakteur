"""Diagnose-Script: dumpt die DOM-Struktur der LinkedIn Top-Posts-Analytics-Seite.

Aufruf:
    uv run python -m apps.onboarding.inspect_top_posts

Nutzt den bereits eingeloggten Persistent-Context unter .playwright_linkedin_profile.
"""

from __future__ import annotations

from eve.utils.windows_console import enable_utf8_console

enable_utf8_console()

import asyncio  # noqa: E402
import json  # noqa: E402

from playwright.async_api import async_playwright  # noqa: E402

URL = (
    "https://www.linkedin.com/analytics/creator/top-posts/"
    "?metricType=ENGAGEMENTS&timeRange=past_365_days"
)


async def main() -> None:
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=".playwright_linkedin_profile",
            headless=False,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
            locale="de-DE",
        )

        page = await context.new_page()
        print(f"Navigiere zu: {URL}")
        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle", timeout=15000)
        await asyncio.sleep(3)

        print(f"Final URL: {page.url}")
        print(f"Title:     {await page.title()}")
        print()

        # Try a bunch of candidate selectors to find the post cards on the analytics page
        diagnostic = await page.evaluate(
            """() => {
            const r = {};

            // Generic count probes
            const probes = [
                'article',
                '[data-test-id]',
                'div[role="listitem"]',
                'li[role="listitem"]',
                'div.member-analytics-addon-entity-list-item',
                'div.member-analytics-addon__cta-list-item',
                '.feed-shared-update-v2',
                '.update-components-text',
                'div[data-urn^="urn:li:activity:"]',
                'a[href*="/feed/update/"]',
                '.artdeco-list__item',
                '[class*="creator-post-list"]',
                '[class*="top-posts"]',
                '[class*="analytics"]'
            ];
            r.probes = {};
            probes.forEach(sel => {
                try { r.probes[sel] = document.querySelectorAll(sel).length; }
                catch (e) { r.probes[sel] = 'err:' + e.message.slice(0,30); }
            });

            // Look for the top-level container with posts
            const allArticleLinks = Array.from(document.querySelectorAll('a[href*="/feed/update/"]'))
                .slice(0, 8)
                .map(a => ({
                    href: a.getAttribute('href'),
                    parentTag: a.parentElement?.tagName,
                    closestListItem: a.closest('li, article, div[role="listitem"]')?.tagName
                }));
            r.activityLinks = allArticleLinks;

            // For the first activity link, dump the bounding container's classes
            const firstLink = document.querySelector('a[href*="/feed/update/"]');
            if (firstLink) {
                let parent = firstLink;
                const chain = [];
                while (parent && chain.length < 8) {
                    chain.push({
                        tag: parent.tagName,
                        classes: (parent.className || '').toString().slice(0, 200),
                        id: parent.id
                    });
                    parent = parent.parentElement;
                }
                r.linkParentChain = chain;
            }

            // Section headings on page
            r.headings = Array.from(document.querySelectorAll('h1, h2, h3'))
                .slice(0, 10)
                .map(h => ({ tag: h.tagName, text: h.innerText.trim().slice(0, 80) }));

            // Any text snippets matching what looks like a post
            const candidates = Array.from(document.querySelectorAll('span, p, div'))
                .filter(el => {
                    const t = (el.innerText || '').trim();
                    return t.length > 80 && t.length < 1500 && t.includes('\\n');
                })
                .slice(0, 5)
                .map(el => ({
                    tag: el.tagName,
                    classes: (el.className || '').toString().slice(0, 200),
                    preview: el.innerText.slice(0, 120)
                }));
            r.textCandidates = candidates;

            return r;
        }"""
        )

        print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
        print()
        input("Drücke ENTER um den Browser zu schließen...")
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
