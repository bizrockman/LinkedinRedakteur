"""Tests für verify_profile_assets()."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from eve.adapters.persistence.fs_prompt_repository import FilesystemPromptRepository
from eve.core.entities import (
    ClientInfo,
    ClientProfile,
    PostSource,
    PostStatus,
    StoredPost,
    SuccessfulPost,
    SyntheticPersona,
    TargetAudience,
)
from eve.use_cases.profile_verification import verify_profile_assets


@pytest.fixture
async def repo():
    with tempfile.TemporaryDirectory() as t:
        Path(t, "templates").mkdir()
        Path(t, "profiles").mkdir()
        # Required templates anlegen (dummy-Inhalt reicht für list_templates)
        for tmpl in ("eve_system", "persona", "wizard_suggest_topics", "wizard_derive_audience"):
            (Path(t) / "templates" / f"{tmpl}.md.j2").write_text("# dummy", encoding="utf-8")
        yield FilesystemPromptRepository(base_dir=t)


def _complete_profile(pid: str = "alice") -> ClientProfile:
    return ClientProfile(
        profile_id=pid,
        client=ClientInfo(name="Alice", description="Beschreibung", topics=["T1", "T2"]),
        audience=TargetAudience(description="Audience-Beschreibung"),
        successful_posts=[SuccessfulPost(text="Hallo Welt")],
        nogos=["Keine Emojis"],
        personas=[SyntheticPersona(name="Nora", role="Test")],
    )


async def test_raises_when_no_profile_and_no_default(repo):
    with pytest.raises(KeyError):
        await verify_profile_assets(repo)


async def test_complete_profile_no_errors_no_warnings_except_posts_sidecar(repo):
    await repo.save_profile(_complete_profile("alice"))
    result = await verify_profile_assets(repo, "alice")
    assert not result.has_errors
    # Posts-Sidecar fehlt → eine Warnung erwartet
    assert any("Posts-Sidecar" in w.name for w in result.warnings)


async def test_default_resolution(repo):
    await repo.save_profile(_complete_profile("alice"))
    # Ohne explizites profile_id → default = alice
    result = await verify_profile_assets(repo)
    assert result.profile_id == "alice"
    assert result.is_default is True


async def test_missing_profile_yields_missing_status(repo):
    # Default existiert nicht, aber wir geben explizit eine ID an
    await repo.save_profile(_complete_profile("alice"))  # default = alice
    result = await verify_profile_assets(repo, "ghost")
    assert result.has_errors
    yaml_check = next(c for c in result.checks if c.name == "Profil-YAML")
    assert yaml_check.status == "missing"


async def test_incomplete_profile_yields_warnings(repo):
    incomplete = ClientProfile(profile_id="bob")  # alle Pflichtfelder leer
    await repo.save_profile(incomplete)
    result = await verify_profile_assets(repo, "bob")
    assert not result.has_errors  # YAML existiert, ist nur unvollständig
    assert result.has_warnings
    fields_check = next(c for c in result.checks if c.name == "Pflichtfelder")
    assert fields_check.status == "warn"


async def test_posts_sidecar_ok_when_present(repo):
    await repo.save_profile(_complete_profile("alice"))
    await repo.save_posts(
        [
            StoredPost(
                text="Imported", source=PostSource.LINKEDIN_IMPORT, status=PostStatus.POSTED
            )
        ],
        profile_id="alice",
    )
    result = await verify_profile_assets(repo, "alice")
    sidecar = next(c for c in result.checks if c.name == "Posts-Sidecar")
    assert sidecar.status == "ok"
    assert "1 Posts" in sidecar.detail


async def test_missing_required_template_is_error(repo):
    await repo.save_profile(_complete_profile("alice"))
    # Required template löschen
    (repo.templates_dir / "eve_system.md.j2").unlink()
    result = await verify_profile_assets(repo, "alice")
    assert result.has_errors
    eve_tmpl = next(c for c in result.checks if "eve_system" in c.name)
    assert eve_tmpl.status == "missing"
