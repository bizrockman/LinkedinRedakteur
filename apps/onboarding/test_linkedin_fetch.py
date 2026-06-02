"""Manueller Test: LinkedIn-Profil scrapen.

Aufruf:
    uv run python -m apps.onboarding.test_linkedin_fetch https://www.linkedin.com/in/<dein-username>/

Erster Lauf öffnet einen sichtbaren Browser für den manuellen Login.
Folgeläufe nutzen den gespeicherten `.linkedin_state.json`.
"""

from __future__ import annotations

from eve.utils.windows_console import enable_utf8_console

enable_utf8_console()

import argparse  # noqa: E402
import asyncio  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from eve.adapters.linkedin.playwright_fetcher import (  # noqa: E402
    PlaywrightLinkedInFetcher,
    dump_snapshot_to_json,
)


async def main(profile_url: str, max_posts: int, out_path: Path | None) -> None:
    fetcher = PlaywrightLinkedInFetcher(
        user_data_dir=".playwright_linkedin_profile",
        headless=False,
        login_timeout=300,
    )
    snapshot = await fetcher.fetch(profile_url, max_posts=max_posts)

    print("\n" + "=" * 60)
    print(f"Profile:   {snapshot.profile_url}")
    print(f"Name:      {snapshot.name}")
    print(f"Headline:  {snapshot.headline}")
    print(f"Location:  {snapshot.location}")
    print(f"About:     {snapshot.about[:200]}{'...' if len(snapshot.about) > 200 else ''}")
    print(f"Posts:     {len(snapshot.posts)}")
    print("=" * 60)

    for i, post in enumerate(snapshot.posts[:5], 1):
        preview = post.text[:160].replace("\n", " ")
        print(f"\n[{i}] {preview}{'...' if len(post.text) > 160 else ''}")

    if out_path:
        dump_snapshot_to_json(snapshot, out_path)
        print(f"\nGespeichert: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LinkedIn-Profil scrapen (Test)")
    parser.add_argument("profile_url", help="z.B. https://www.linkedin.com/in/username/")
    parser.add_argument("--max-posts", type=int, default=15)
    parser.add_argument("--out", type=Path, default=None, help="Snapshot als JSON speichern")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        asyncio.run(main(args.profile_url, args.max_posts, args.out))
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        sys.exit(130)
