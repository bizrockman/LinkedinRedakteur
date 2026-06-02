"""verify_profile_assets — checkt, ob alle Assets eines Profils vorhanden sind.

UI-agnostische Use Case: liefert ein strukturiertes Result, das CLIs/Web-Adapter
in einer Tabelle, JSON oder Statusbalken anzeigen können.

Geprüft werden:
- Profil-YAML existiert und ist parsbar
- Pflichtfelder gefüllt (siehe ClientProfile.is_complete())
- Posts-Sidecar (optional; Warnung statt Fehler)
- Pflicht-Templates (eve_system, persona)
- Wizard-Templates (optional; Warnung)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from eve.core.ports import PromptRepository

CheckStatus = Literal["ok", "warn", "missing"]

REQUIRED_TEMPLATES = ("eve_system", "persona")
OPTIONAL_TEMPLATES = ("wizard_suggest_topics", "wizard_derive_audience")


@dataclass(frozen=True)
class AssetCheck:
    """Ergebnis eines einzelnen Asset-Checks."""

    name: str
    status: CheckStatus
    detail: str = ""


@dataclass(frozen=True)
class ProfileVerificationResult:
    profile_id: str
    is_default: bool
    checks: list[AssetCheck] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(c.status == "missing" for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(c.status == "warn" for c in self.checks)

    @property
    def errors(self) -> list[AssetCheck]:
        return [c for c in self.checks if c.status == "missing"]

    @property
    def warnings(self) -> list[AssetCheck]:
        return [c for c in self.checks if c.status == "warn"]


async def verify_profile_assets(
    prompts: PromptRepository,
    profile_id: str | None = None,
) -> ProfileVerificationResult:
    """Prüft alle Assets eines Profils.

    Wenn `profile_id` None ist, wird das aktuelle Default-Profil geprüft.
    Wirft KeyError nur, wenn weder das angegebene noch ein Default-Profil existiert.
    """
    checks: list[AssetCheck] = []

    # --- Profile-Resolution ---
    default_id = await prompts.get_default_profile_id()
    resolved_id = profile_id or default_id
    if resolved_id is None:
        raise KeyError(
            "Kein Profil angegeben und kein Default gesetzt. "
            "Starte den Onboarding-Wizard via `python -m apps.onboarding.cli`."
        )
    is_default = default_id == resolved_id

    # --- Profile YAML ---
    try:
        profile = await prompts.get_profile(resolved_id)
        checks.append(
            AssetCheck(
                name="Profil-YAML",
                status="ok",
                detail=f"{resolved_id}.yaml (geladen, valide)",
            )
        )
    except KeyError as e:
        checks.append(AssetCheck(name="Profil-YAML", status="missing", detail=str(e)))
        return ProfileVerificationResult(
            profile_id=resolved_id, is_default=is_default, checks=checks
        )

    # --- Pflichtfelder ---
    if profile.is_complete():
        checks.append(
            AssetCheck(
                name="Pflichtfelder",
                status="ok",
                detail="Alle Pflichtfelder gefüllt",
            )
        )
    else:
        missing = ", ".join(profile.missing_fields())
        checks.append(
            AssetCheck(
                name="Pflichtfelder",
                status="warn",
                detail=f"Fehlend: {missing}",
            )
        )

    # --- Einzel-Counts (nice-to-have, gibt Übersicht) ---
    checks.append(
        AssetCheck(
            name="Themen",
            status="ok" if profile.client.topics else "warn",
            detail=f"{len(profile.client.topics)} Themen",
        )
    )
    checks.append(
        AssetCheck(
            name="Personas",
            status="ok" if profile.personas else "warn",
            detail=f"{len(profile.personas)} Persona(s)",
        )
    )
    checks.append(
        AssetCheck(
            name="Erfolgreichste Posts (Stil-Anker)",
            status="ok" if profile.successful_posts else "warn",
            detail=f"{len(profile.successful_posts)} Posts",
        )
    )
    checks.append(
        AssetCheck(
            name="NoGos",
            status="ok" if profile.nogos else "warn",
            detail=f"{len(profile.nogos)} Einträge",
        )
    )

    # --- Posts-Sidecar (Historie, optional) ---
    posts = await prompts.load_posts(resolved_id)
    checks.append(
        AssetCheck(
            name="Posts-Sidecar",
            status="ok" if posts else "warn",
            detail=f"{len(posts)} Posts in {resolved_id}.posts.json",
        )
    )

    # --- Templates ---
    available = set(await prompts.list_templates())
    for name in REQUIRED_TEMPLATES:
        checks.append(
            AssetCheck(
                name=f"Template '{name}'",
                status="ok" if name in available else "missing",
                detail=f"{name}.md.j2",
            )
        )
    for name in OPTIONAL_TEMPLATES:
        checks.append(
            AssetCheck(
                name=f"Template '{name}'",
                status="ok" if name in available else "warn",
                detail=f"{name}.md.j2 (optional, für Wizard)",
            )
        )

    return ProfileVerificationResult(
        profile_id=resolved_id, is_default=is_default, checks=checks
    )
