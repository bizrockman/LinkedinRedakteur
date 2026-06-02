"""Tests für die JSON-Sidecar-Storage der StoredPosts."""

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
)


@pytest.fixture
async def repo():
    with tempfile.TemporaryDirectory() as t:
        Path(t, "templates").mkdir()
        Path(t, "profiles").mkdir()
        r = FilesystemPromptRepository(base_dir=t)
        # Default-Profile anlegen
        await r.save_profile(
            ClientProfile(
                profile_id="alice",
                client=ClientInfo(name="Alice", description="x", topics=["T"]),
            )
        )
        yield r


def _post(text: str, source: PostSource = PostSource.LINKEDIN_IMPORT) -> StoredPost:
    return StoredPost(text=text, source=source, status=PostStatus.POSTED)


async def test_load_returns_empty_when_no_file(repo):
    assert await repo.load_posts("alice") == []


async def test_save_then_load_roundtrip(repo):
    posts = [_post("Erster"), _post("Zweiter"), _post("Dritter")]
    await repo.save_posts(posts, profile_id="alice")
    loaded = await repo.load_posts("alice")
    assert len(loaded) == 3
    assert [p.text for p in loaded] == ["Erster", "Zweiter", "Dritter"]
    # IDs are preserved
    assert {p.id for p in loaded} == {p.id for p in posts}


async def test_save_overwrites(repo):
    await repo.save_posts([_post("Erster")], profile_id="alice")
    await repo.save_posts([_post("Komplett anderer")], profile_id="alice")
    loaded = await repo.load_posts("alice")
    assert len(loaded) == 1
    assert loaded[0].text == "Komplett anderer"


async def test_uses_default_profile_when_none_given(repo):
    posts = [_post("Default-Profile-Post")]
    await repo.save_posts(posts)  # no profile_id
    loaded = await repo.load_posts()
    assert len(loaded) == 1
    assert loaded[0].text == "Default-Profile-Post"


async def test_save_without_default_raises(repo):
    # Delete the default
    await repo.delete_profile("alice")
    with pytest.raises(KeyError):
        await repo.save_posts([_post("nope")])


async def test_source_enum_preserved(repo):
    posts = [
        _post("eve-post", source=PostSource.EVE),
        _post("import-post", source=PostSource.LINKEDIN_IMPORT),
        _post("gdpr-post", source=PostSource.GDPR_IMPORT),
    ]
    await repo.save_posts(posts, profile_id="alice")
    loaded = await repo.load_posts("alice")
    sources = [p.source for p in loaded]
    assert PostSource.EVE in sources
    assert PostSource.LINKEDIN_IMPORT in sources
    assert PostSource.GDPR_IMPORT in sources
