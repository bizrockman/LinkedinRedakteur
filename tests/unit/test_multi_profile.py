"""Multi-Profile-Logik im FilesystemPromptRepository."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from eve.adapters.persistence.fs_prompt_repository import FilesystemPromptRepository
from eve.core.entities import ClientInfo, ClientProfile


@pytest.fixture
async def repo():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "templates").mkdir()
        Path(tmp, "profiles").mkdir()
        yield FilesystemPromptRepository(base_dir=tmp)


def _profile(pid: str) -> ClientProfile:
    return ClientProfile(
        profile_id=pid,
        client=ClientInfo(name=pid.capitalize(), description="x", topics=["T"]),
    )


async def test_no_default_initially(repo):
    assert await repo.get_default_profile_id() is None


async def test_first_save_becomes_default(repo):
    await repo.save_profile(_profile("alice"))
    assert await repo.get_default_profile_id() == "alice"


async def test_second_save_does_not_steal_default(repo):
    await repo.save_profile(_profile("alice"))
    await repo.save_profile(_profile("bob"))
    assert await repo.get_default_profile_id() == "alice"


async def test_get_profile_no_arg_returns_default(repo):
    await repo.save_profile(_profile("alice"))
    loaded = await repo.get_profile()
    assert loaded.profile_id == "alice"


async def test_get_profile_no_default_raises(repo):
    with pytest.raises(KeyError):
        await repo.get_profile()


async def test_get_profile_unknown_raises(repo):
    with pytest.raises(KeyError):
        await repo.get_profile("ghost")


async def test_explicit_set_default(repo):
    await repo.save_profile(_profile("alice"))
    await repo.save_profile(_profile("bob"))
    await repo.set_default_profile_id("bob")
    assert await repo.get_default_profile_id() == "bob"


async def test_set_default_for_unknown_raises(repo):
    with pytest.raises(KeyError):
        await repo.set_default_profile_id("ghost")


async def test_delete_default_clears_pointer(repo):
    await repo.save_profile(_profile("alice"))
    await repo.delete_profile("alice")
    assert await repo.get_default_profile_id() is None


async def test_delete_non_default_keeps_pointer(repo):
    await repo.save_profile(_profile("alice"))
    await repo.save_profile(_profile("bob"))
    await repo.delete_profile("bob")
    assert await repo.get_default_profile_id() == "alice"


async def test_list_profiles(repo):
    assert await repo.list_profiles() == []
    await repo.save_profile(_profile("alice"))
    await repo.save_profile(_profile("bob"))
    assert await repo.list_profiles() == ["alice", "bob"]
