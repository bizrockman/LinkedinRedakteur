"""Manueller Test: GDPR-Export einlesen.

Aufruf:
    uv run python -m apps.onboarding.test_gdpr_fetch <pfad/zur/export.zip>
"""

from __future__ import annotations

from eve.utils.windows_console import enable_utf8_console

enable_utf8_console()

import argparse  # noqa: E402
import asyncio  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from eve.adapters.linkedin.gdpr_export_fetcher import GdprExportLinkedInFetcher  # noqa: E402
from eve.adapters.linkedin.playwright_fetcher import dump_snapshot_to_json  # noqa: E402


async def main(export_path: Path, max_posts: int, out_path: Path | None) -> None:
    fetcher = GdprExportLinkedInFetcher(export_path, include_articles=True)
    snap = await fetcher.fetch(max_posts=max_posts)

    print("=" * 60)
    print(f"Source:    {fetcher.source_name}")
    print(f"Name:      {snap.name}")
    print(f"Headline:  {snap.headline}")
    print(f"Location:  {snap.location}")
    print()
    print("About:")
    print(snap.about[:800])
    if len(snap.about) > 800:
        print("...")
    print()
    print(f"Posts:     {len(snap.posts)}")
    for i, p in enumerate(snap.posts[:5], 1):
        preview = p.text[:160].replace("\n", " ")
        print(f"  [{i}] ({p.posted_at}) {preview}")

    print()
    print("Raw profile keys:", list(snap.raw.get("profile_csv", {}).keys()))

    if out_path:
        dump_snapshot_to_json(snap, out_path)
        print(f"\nGespeichert: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LinkedIn GDPR-Export einlesen")
    parser.add_argument("export_path", type=Path, help="Pfad zur ZIP oder zum entpackten Ordner")
    parser.add_argument("--max-posts", type=int, default=25)
    parser.add_argument("--out", type=Path, default=None, help="Snapshot als JSON speichern")
    args = parser.parse_args()

    if not args.export_path.exists():
        print(f"ERROR: {args.export_path} nicht gefunden", file=sys.stderr)
        sys.exit(1)

    asyncio.run(main(args.export_path, args.max_posts, args.out))
