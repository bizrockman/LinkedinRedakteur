"""Typed application settings loaded from environment variables (.env)."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_REF_RE = re.compile(r"^https?://([a-z0-9]+)\.supabase\.co/?", re.IGNORECASE)


def _extract_supabase_project_ref(url: str) -> str | None:
    """Extrahiert den Project-Ref aus einer Supabase-Cloud-URL.

    `https://twggayqzijrxjirwsoqz.supabase.co` → `twggayqzijrxjirwsoqz`

    Bei Self-Hosted-URLs (eigene Domain) wird None zurückgegeben — dort
    muss der User dann SUPABASE_DB_URL explicit setzen.
    """
    m = _PROJECT_REF_RE.match(url.strip())
    return m.group(1) if m else None


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProviderName(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OPENROUTER = "openrouter"


class Settings(BaseSettings):
    """Top-level config. Read from .env or process env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App
    env: Environment = Field(default=Environment.DEVELOPMENT, alias="EVE_ENV")
    log_level: str = Field(default="INFO", alias="EVE_LOG_LEVEL")
    port: int = Field(default=8000, alias="EVE_PORT")

    # --- Supabase --------------------------------------------------------
    # Eve nutzt den offiziellen supabase-py Client. Damit reichen URL + Key.
    #
    # Project-URL (Cloud `https://<ref>.supabase.co`) oder Self-Host-URL.
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    # Server-Side Admin-Key. Funktioniert mit BEIDEN Formaten:
    #   - Alt:  service_role JWT (eyJhbGc...)
    #   - Neu:  sb_secret_xxx
    supabase_service_key: SecretStr | None = Field(default=None, alias="SUPABASE_SERVICE_KEY")
    supabase_storage_bucket: str = Field(default="eve-media", alias="SUPABASE_STORAGE_BUCKET")

    # --- LLM
    llm_default_provider: LLMProviderName = Field(
        default=LLMProviderName.ANTHROPIC, alias="EVE_LLM_DEFAULT_PROVIDER"
    )
    llm_default_model: str = Field(default="claude-opus-4-7", alias="EVE_LLM_DEFAULT_MODEL")
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openrouter_api_key: SecretStr | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_default_providers: str = Field(
        default="Anthropic,OpenAI", alias="OPENROUTER_DEFAULT_PROVIDERS"
    )

    # --- Image generation
    # Reference-Bilder (für konsistente Identität in generierten Posts) liegen
    # in Supabase Storage unter <BUCKET>/references/. Einfach Bilder dort
    # uploaden — Eve listet & nutzt sie automatisch zur Laufzeit.
    fal_api_key: SecretStr | None = Field(default=None, alias="FAL_API_KEY")
    fal_image_model: str = Field(
        default="fal-ai/bytedance/seedream/v4.5/edit", alias="FAL_IMAGE_MODEL"
    )
    fal_references_path: str = Field(default="references", alias="FAL_REFERENCES_PATH")

    # --- Telegram
    telegram_bot_token: SecretStr | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_url: str = Field(default="", alias="TELEGRAM_WEBHOOK_URL")
    telegram_webhook_secret: SecretStr | None = Field(
        default=None, alias="TELEGRAM_WEBHOOK_SECRET"
    )

    # --- Slack (optional Phase 2)
    slack_bot_token: SecretStr | None = Field(default=None, alias="SLACK_BOT_TOKEN")
    slack_signing_secret: SecretStr | None = Field(default=None, alias="SLACK_SIGNING_SECRET")

    # --- LinkedIn
    linkedin_access_token: SecretStr | None = Field(default=None, alias="LINKEDIN_ACCESS_TOKEN")
    linkedin_person_urn: str = Field(default="", alias="LINKEDIN_PERSON_URN")

    # --- Scheduler
    daily_post_hour_utc: int = Field(default=7, alias="EVE_DAILY_POST_HOUR_UTC")

    # --- Encryption Master-Key (Fernet, 32-byte url-safe base64)
    # Verschlüsselt OAuth-Tokens client-side bevor sie nach Supabase wandern.
    # Generiere einen neuen Key mit:
    #   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    eve_master_key: SecretStr | None = Field(default=None, alias="EVE_MASTER_KEY")

    @property
    def supabase_project_ref(self) -> str | None:
        """Project-Ref aus der Cloud-URL extrahiert. None bei Self-Hosted.

        Wird genutzt für Deep-Links ins Supabase-Dashboard (z.B. SQL Editor).
        """
        return _extract_supabase_project_ref(self.supabase_url)

    @property
    def openrouter_providers_list(self) -> list[str]:
        return [p.strip() for p in self.openrouter_default_providers.split(",") if p.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    """Cached settings instance. Tests can override via dependency injection."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
