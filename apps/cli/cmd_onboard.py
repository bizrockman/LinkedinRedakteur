"""eve onboard — Wizard durchlaufen. Wrapper auf apps.onboarding.cli."""

from __future__ import annotations

import asyncio
import sys

from apps.onboarding import cli as onboard_cli


def run_onboarding(profile_id: str, model: str | None = None) -> None:
    """Führt den Onboarding-Wizard aus."""
    exit_code = asyncio.run(onboard_cli.run(profile_id, model))
    sys.exit(exit_code)
