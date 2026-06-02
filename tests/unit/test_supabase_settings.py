"""Tests für die Supabase-Settings (URL-Parsing, Project-Ref-Extraction)."""

from __future__ import annotations

from eve.config.settings import Settings, _extract_supabase_project_ref


def test_extract_project_ref_from_cloud_url():
    assert _extract_supabase_project_ref("https://twggayqzijrxjirwsoqz.supabase.co") == (
        "twggayqzijrxjirwsoqz"
    )
    assert _extract_supabase_project_ref("https://abc123xyz.supabase.co/") == "abc123xyz"


def test_extract_project_ref_self_host_returns_none():
    assert _extract_supabase_project_ref("https://supabase.bizrock.de") is None
    assert _extract_supabase_project_ref("https://internal.company.com") is None


def test_extract_project_ref_empty():
    assert _extract_supabase_project_ref("") is None


def test_project_ref_property_via_settings():
    s = Settings.model_construct(supabase_url="https://abc123.supabase.co")
    assert s.supabase_project_ref == "abc123"

    s2 = Settings.model_construct(supabase_url="https://self.host.de")
    assert s2.supabase_project_ref is None
