"""Transcriber + Vision ports — content extraction from media files."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AudioTranscriber(Protocol):
    """Speech-to-text (Whisper, etc.)."""

    async def transcribe(self, *, audio: bytes, mime_type: str, language: str | None = None) -> str: ...


@runtime_checkable
class VisionAnalyzer(Protocol):
    """Vision-LM: describe image content."""

    async def describe(self, *, image: bytes, mime_type: str, prompt: str | None = None) -> str: ...
