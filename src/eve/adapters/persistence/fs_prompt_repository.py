"""Filesystem-Adapter für PromptRepository.

Layout:
    prompts/
        templates/
            eve_system.md.j2
            persona.md.j2
        profiles/
            default.yaml
            <other>.yaml

Templates: Jinja2 mit `StrictUndefined` — fehlende Variablen werfen sofort.
Profiles: YAML, deserialisiert nach `ClientProfile`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from eve.core.entities import ClientProfile, PromptTemplate, RenderedPrompt, StoredPost

TEMPLATE_SUFFIX = ".md.j2"
PROFILE_SUFFIX = ".yaml"
POSTS_SUFFIX = ".posts.json"
DEFAULT_POINTER_FILE = ".default"


class FilesystemPromptRepository:
    """Liest Templates und Profile vom Dateisystem; rendert via Jinja2."""

    def __init__(self, base_dir: Path | str = "prompts") -> None:
        self.base_dir = Path(base_dir).resolve()
        self.templates_dir = self.base_dir / "templates"
        self.profiles_dir = self.base_dir / "profiles"
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        self._jinja = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
            autoescape=False,  # Prompts sind kein HTML
        )

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------
    async def get_template(self, name: str) -> PromptTemplate:
        path = self.templates_dir / f"{name}{TEMPLATE_SUFFIX}"
        if not path.exists():
            raise KeyError(f"Template '{name}' not found at {path}")

        body = path.read_text(encoding="utf-8")
        return PromptTemplate(
            name=name,
            body=body,
            updated_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
        )

    async def list_templates(self) -> list[str]:
        return sorted(
            p.name.removesuffix(TEMPLATE_SUFFIX)
            for p in self.templates_dir.glob(f"*{TEMPLATE_SUFFIX}")
        )

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------
    @property
    def _default_pointer(self) -> Path:
        return self.profiles_dir / DEFAULT_POINTER_FILE

    async def get_default_profile_id(self) -> str | None:
        if not self._default_pointer.exists():
            return None
        content = self._default_pointer.read_text(encoding="utf-8").strip()
        return content or None

    async def set_default_profile_id(self, profile_id: str) -> None:
        path = self.profiles_dir / f"{profile_id}{PROFILE_SUFFIX}"
        if not path.exists():
            raise KeyError(f"Cannot set default — profile '{profile_id}' does not exist")
        self._default_pointer.write_text(profile_id, encoding="utf-8")

    async def get_profile(self, profile_id: str | None = None) -> ClientProfile:
        if profile_id is None:
            default = await self.get_default_profile_id()
            if default is None:
                raise KeyError("No default profile set and no profile_id given")
            profile_id = default

        path = self.profiles_dir / f"{profile_id}{PROFILE_SUFFIX}"
        if not path.exists():
            raise KeyError(f"Profile '{profile_id}' not found at {path}")

        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        data.setdefault("profile_id", profile_id)
        return ClientProfile.model_validate(data)

    async def save_profile(self, profile: ClientProfile) -> ClientProfile:
        path = self.profiles_dir / f"{profile.profile_id}{PROFILE_SUFFIX}"
        now = datetime.now(UTC)
        if profile.created_at is None:
            profile.created_at = now
        profile.updated_at = now

        # `mode="json"` serialisiert datetime/enum sauber für YAML
        payload = profile.model_dump(mode="json")
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False, indent=2)

        # First profile created becomes default automatically
        if await self.get_default_profile_id() is None:
            await self.set_default_profile_id(profile.profile_id)

        return profile

    async def delete_profile(self, profile_id: str) -> None:
        path = self.profiles_dir / f"{profile_id}{PROFILE_SUFFIX}"
        if path.exists():
            path.unlink()
        # Clear default pointer if it pointed to this profile
        if await self.get_default_profile_id() == profile_id:
            self._default_pointer.unlink(missing_ok=True)

    async def list_profiles(self) -> list[str]:
        return sorted(
            p.name.removesuffix(PROFILE_SUFFIX)
            for p in self.profiles_dir.glob(f"*{PROFILE_SUFFIX}")
        )

    # ------------------------------------------------------------------
    # Posts (sidecar JSON; später Supabase)
    # ------------------------------------------------------------------
    def _posts_path(self, profile_id: str) -> Path:
        return self.profiles_dir / f"{profile_id}{POSTS_SUFFIX}"

    async def _resolve_profile_id(self, profile_id: str | None) -> str:
        if profile_id is not None:
            return profile_id
        default = await self.get_default_profile_id()
        if default is None:
            raise KeyError("No profile_id given and no default set")
        return default

    async def load_posts(self, profile_id: str | None = None) -> list[StoredPost]:
        pid = await self._resolve_profile_id(profile_id)
        path = self._posts_path(pid)
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"Expected list in {path}, got {type(data).__name__}")
        return [StoredPost.model_validate(p) for p in data]

    async def save_posts(
        self, posts: list[StoredPost], *, profile_id: str | None = None
    ) -> None:
        pid = await self._resolve_profile_id(profile_id)
        path = self._posts_path(pid)
        payload = [p.model_dump(mode="json") for p in posts]
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    async def render(
        self,
        template_name: str,
        *,
        profile_id: str | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> RenderedPrompt:
        try:
            jinja_template = self._jinja.get_template(f"{template_name}{TEMPLATE_SUFFIX}")
        except TemplateNotFound as e:
            raise KeyError(f"Template '{template_name}' not found") from e

        profile = await self.get_profile(profile_id)
        resolved_id = profile.profile_id
        context: dict[str, Any] = {
            "profile": profile,
            "agent": profile.agent,
            "client": profile.client,
            "audience": profile.audience,
            "successful_posts": profile.successful_posts,
            "nogos": profile.nogos,
            "personas": profile.personas,
        }
        if extra_context:
            context.update(extra_context)

        body = jinja_template.render(**context)
        return RenderedPrompt(
            template_name=template_name,
            profile_id=resolved_id,
            body=body,
            variables={k: (v if isinstance(v, str | int | float | bool) else "...") for k, v in context.items()},
        )

    async def render_raw(
        self,
        template_name: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> RenderedPrompt:
        """Rendert ohne Profil-Lookup. Für Wizard-Templates, die ihren
        gesamten Context selbst mitbringen."""
        try:
            jinja_template = self._jinja.get_template(f"{template_name}{TEMPLATE_SUFFIX}")
        except TemplateNotFound as e:
            raise KeyError(f"Template '{template_name}' not found") from e

        ctx = context or {}
        body = jinja_template.render(**ctx)
        return RenderedPrompt(
            template_name=template_name,
            profile_id="",
            body=body,
            variables={k: (v if isinstance(v, str | int | float | bool) else "...") for k, v in ctx.items()},
        )
