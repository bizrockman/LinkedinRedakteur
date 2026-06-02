"""Composition root — wires Adapters into Ports.

Tausch von Supabase ↔ Baserow ↔ Anthropic ↔ OpenAI passiert ausschliesslich hier.
Kein Code in `core/` oder `agent/` darf Adapter direkt importieren.

We use a hand-rolled Container instead of `dependency-injector` to keep the
dependency graph readable and traceable. Each port resolves lazily on first
access via @cached_property. Tests instantiate Container directly with stubs.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

from eve.config.settings import LLMProviderName, Settings, get_settings
from eve.core.ports import (
    AudioTranscriber,
    ChatMemory,
    FileStorage,
    ImageGenerator,
    LLMProvider,
    PostsRepository,
    PromptRepository,
    SocialPublisher,
    VisionAnalyzer,
)


class Container:
    """Application composition root.

    Resolves all ports lazily so import-time has zero side effects.
    Override any property in tests by subclassing or setting attributes
    directly before first access.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    @cached_property
    def supabase(self):
        """Geteilter supabase-py Client für Posts / Chat / Storage."""
        from supabase import create_client

        if not self.settings.supabase_url or not self.settings.supabase_service_key:
            raise RuntimeError(
                "SUPABASE_URL und SUPABASE_SERVICE_KEY müssen in .env gesetzt sein."
            )
        return create_client(
            self.settings.supabase_url,
            self.settings.supabase_service_key.get_secret_value(),
        )

    @cached_property
    def posts_repository(self) -> PostsRepository:
        """Supabase-basiertes Posts-Repository.

        Noch nicht implementiert — Posts werden aktuell als JSON-Sidecar
        gespeichert (siehe `prompts.save_posts() / prompts.load_posts()`).
        Wird aktiviert, sobald wir den Eve-Agent von Filesystem auf
        DB umstellen.
        """
        raise NotImplementedError(
            "SupabasePostsRepository wird noch implementiert. "
            "Aktuell: Posts liegen im JSON-Sidecar (FilesystemPromptRepository)."
        )

    @cached_property
    def chat_memory(self) -> ChatMemory:
        """Persistente Chat-History für den Eve-Agent.

        Noch nicht implementiert — der Agent läuft heute stateless.
        Wird aktiviert, sobald der Agent-Conversation-Loop steht.
        """
        raise NotImplementedError(
            "SupabaseChatMemory wird noch implementiert. "
            "Aktuell: Eve-Agent läuft stateless ohne Multi-Turn-Memory."
        )

    # Adapter werden später mit `eve_*`-Tabellen im public schema arbeiten —
    # kein Schema-Argument nötig, da supabase-py defaultmäßig public nutzt.

    @cached_property
    def prompts(self) -> PromptRepository:
        """Prompt-Templates und Client-Profile.

        Default: Filesystem (prompts/templates + prompts/profiles).
        Tausch gegen Supabase-basierten Adapter erfolgt hier.
        """
        from eve.adapters.persistence.fs_prompt_repository import FilesystemPromptRepository

        # Sucht "prompts/" relativ zum Projekt-Root (zwei Ebenen über src/eve/config/).
        project_root = Path(__file__).resolve().parents[3]
        return FilesystemPromptRepository(base_dir=project_root / "prompts")

    @cached_property
    def file_storage(self) -> FileStorage:
        from eve.adapters.persistence.supabase_storage import SupabaseStorageAdapter

        if not self.settings.supabase_service_key:
            raise RuntimeError("SUPABASE_SERVICE_KEY required for FileStorage")
        return SupabaseStorageAdapter(
            url=self.settings.supabase_url,
            service_key=self.settings.supabase_service_key.get_secret_value(),
        )

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------
    @cached_property
    def llm(self) -> LLMProvider:
        """The default LLM provider used by the Eve agent."""
        return self._build_llm(self.settings.llm_default_provider)

    def _build_llm(self, provider: LLMProviderName) -> LLMProvider:
        """Factory for building an LLM provider by name. Lazy-imports adapters."""
        if provider is LLMProviderName.ANTHROPIC:
            from eve.adapters.llm.anthropic_provider import AnthropicProvider

            if not self.settings.anthropic_api_key:
                raise RuntimeError("ANTHROPIC_API_KEY missing")
            return AnthropicProvider(api_key=self.settings.anthropic_api_key.get_secret_value())

        if provider is LLMProviderName.OPENAI:
            from eve.adapters.llm.openai_provider import OpenAIProvider

            if not self.settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY missing")
            return OpenAIProvider(api_key=self.settings.openai_api_key.get_secret_value())

        if provider is LLMProviderName.OPENROUTER:
            from eve.adapters.llm.openrouter_provider import OpenRouterProvider

            if not self.settings.openrouter_api_key:
                raise RuntimeError("OPENROUTER_API_KEY missing")
            return OpenRouterProvider(
                api_key=self.settings.openrouter_api_key.get_secret_value(),
                default_providers=self.settings.openrouter_providers_list,
            )

        raise ValueError(f"Unknown LLM provider: {provider}")

    # ------------------------------------------------------------------
    # Media: vision, transcription, image generation
    # ------------------------------------------------------------------
    @cached_property
    def vision(self) -> VisionAnalyzer:
        from eve.adapters.llm.openai_vision import OpenAIVisionAnalyzer

        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY required for vision")
        return OpenAIVisionAnalyzer(api_key=self.settings.openai_api_key.get_secret_value())

    @cached_property
    def transcriber(self) -> AudioTranscriber:
        from eve.adapters.llm.openai_whisper import OpenAIWhisperTranscriber

        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY required for transcription")
        return OpenAIWhisperTranscriber(api_key=self.settings.openai_api_key.get_secret_value())

    @cached_property
    def image_generator(self) -> ImageGenerator:
        """fal.ai Seedream Image-Generator.

        Reference-Bilder (für konsistente Identität) werden zur Laufzeit aus
        dem Supabase-Storage-Bucket `<SUPABASE_STORAGE_BUCKET>/references/`
        gelistet — kein ENV-Listing nötig, einfach Bilder ins Bucket schieben.
        """
        from eve.adapters.images.fal_seedream import FalSeedreamGenerator

        if not self.settings.fal_api_key:
            raise RuntimeError("FAL_API_KEY missing")
        return FalSeedreamGenerator(
            api_key=self.settings.fal_api_key.get_secret_value(),
            model=self.settings.fal_image_model,
            supabase_client=self.supabase,
            bucket=self.settings.supabase_storage_bucket,
            references_path=self.settings.fal_references_path,
        )

    # ------------------------------------------------------------------
    # Publishers
    # ------------------------------------------------------------------
    @cached_property
    def linkedin_publisher(self) -> SocialPublisher:
        from eve.adapters.publishers.linkedin_publisher import LinkedInPublisher

        if not self.settings.linkedin_access_token:
            raise RuntimeError("LINKEDIN_ACCESS_TOKEN missing")
        return LinkedInPublisher(
            access_token=self.settings.linkedin_access_token.get_secret_value(),
            person_urn=self.settings.linkedin_person_urn,
        )


_container: Container | None = None


def get_container() -> Container:
    """Lazy global container. Tests should construct Container() directly."""
    global _container
    if _container is None:
        _container = Container()
    return _container
