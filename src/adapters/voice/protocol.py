"""Voice provider seams (PLAN-02 P16).

Two protocols, deliberately narrow: one call each, no client-library abstraction. The whole
point of a seam here is that `VoiceCascade` can be handed a stub in a test and a real provider
in production without either knowing about the other -- which is also what lets gate 16.3
prove the *cascade* selects tier 1 without needing a live ElevenLabs key.
"""

from __future__ import annotations

import os
from typing import Protocol

#: Env var names, in one place. Read at call time rather than import time so a process that
#: boots without keys still starts (CONSTITUTION III.7) and a key exported later is picked up
#: without a restart.
ENV_ELEVENLABS_KEY = "ELEVENLABS_API_KEY"
ENV_ELEVENLABS_VOICE = "ELEVENLABS_VOICE_ID"
ENV_GROQ_KEY = "GROQ_API_KEY"
ENV_OPENAI_KEY = "OPENAI_API_KEY"


class VoiceError(RuntimeError):
    """A provider call failed. Always recoverable by the cascade -- never raised past it."""


class QuotaExhausted(VoiceError):
    """The provider is out of credit, as opposed to broken.

    Distinguished from a generic `VoiceError` because the two deserve different operational
    responses -- a quota is a billing fact that will not fix itself on retry, while a 502 might
    -- even though the cascade degrades identically for both. `PLAN-01` P12 recorded that
    ElevenLabs signals this in the error body rather than by status code alone.
    """


class SpeechSynthesizer(Protocol):
    """Text in, audio bytes out."""

    @property
    def name(self) -> str: ...

    def is_configured(self) -> bool:
        """Whether this provider has what it needs to be tried at all."""
        ...

    async def speak(self, text: str, *, voice_id: str | None = None) -> bytes: ...


class SpeechTranscriber(Protocol):
    """Audio bytes in, text out."""

    @property
    def name(self) -> str: ...

    def is_configured(self) -> bool: ...

    async def transcribe(self, audio: bytes, *, mime_type: str) -> str: ...


def env_key(name: str) -> str | None:
    """`None` for unset *and* for empty-string, which is what a `.env` line like
    `ELEVENLABS_API_KEY=` actually produces -- treating that as "configured" is how a
    provider gets tried with an empty bearer token and fails confusingly."""
    return os.environ.get(name) or None
