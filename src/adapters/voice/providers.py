"""Tier-1 voice providers (PLAN-02 P16): ElevenLabs for speech out, Whisper for speech in.

Plain `httpx`, not each vendor's SDK -- the same call this module makes is one POST, and
`src/agent/providers.py` already established that pattern for the model providers rather than
adding a client library per vendor.

**No key values live here or anywhere in this repository.** Every credential is read from the
environment at call time; gate 16.11 scans source and both lockfiles to keep it that way.
"""

from __future__ import annotations

from typing import Any, Final

import httpx

from src.adapters.voice.protocol import (
    ENV_ELEVENLABS_KEY,
    ENV_ELEVENLABS_VOICE,
    ENV_GROQ_KEY,
    ENV_OPENAI_KEY,
    QuotaExhausted,
    VoiceError,
    env_key,
)

_TIMEOUT_S: Final[float] = 30.0

#: `eleven_turbo_v2_5` is the low-latency model PLAN-02 P16 names -- quality is close enough
#: to the flagship that the latency difference is the one a listener actually notices in a
#: back-and-forth conversation.
ELEVENLABS_MODEL: Final[str] = "eleven_turbo_v2_5"
ELEVENLABS_BASE: Final[str] = "https://api.elevenlabs.io/v1"

#: A widely-available stock voice, used when no `ELEVENLABS_VOICE_ID` is set. Named as a
#: default rather than hardcoded at the call site so the picker and the fallback agree.
DEFAULT_VOICE_ID: Final[str] = "21m00Tcm4TlvDq8ikWAM"

#: Groq's free tier serves `whisper-large-v3-turbo`, which is why it is tier 1's first choice
#: (PLAN-02 P16); OpenAI is the paid fallback *within* tier 1, before the cascade drops to the
#: browser at all.
GROQ_WHISPER_MODEL: Final[str] = "whisper-large-v3-turbo"
GROQ_TRANSCRIBE_URL: Final[str] = "https://api.groq.com/openai/v1/audio/transcriptions"
OPENAI_WHISPER_MODEL: Final[str] = "whisper-1"
OPENAI_TRANSCRIBE_URL: Final[str] = "https://api.openai.com/v1/audio/transcriptions"

#: Substrings ElevenLabs puts in an error body when the account is out of credit rather than
#: broken. Checked case-insensitively against the response text, because the status code alone
#: is a 401 in some of these cases and a 429 in others (PLAN-01 P12's own note).
_QUOTA_MARKERS: Final[tuple[str, ...]] = (
    "quota_exceeded",
    "payment_required",
    "paid_plan",
    "insufficient_credit",
    "exceeds your quota",
)


def _is_quota(body: str) -> bool:
    lowered = body.lower()
    return any(marker in lowered for marker in _QUOTA_MARKERS)


class ElevenLabsSynthesizer:
    """Speech out, tier 1."""

    @property
    def name(self) -> str:
        return "elevenlabs"

    def is_configured(self) -> bool:
        return env_key(ENV_ELEVENLABS_KEY) is not None

    async def list_voices(self) -> tuple[tuple[str, str], ...]:
        """`(voice_id, name)` for the voices **this account may actually use**.

        Hardcoding well-known library voice ids looks convenient and fails on a free account:
        ElevenLabs answers `paid_plan_required` -- *"Free users cannot use library voices via
        the API"* -- so every call degrades to the browser while `capabilities` cheerfully
        reports tier 1. Asking the account what it has is the only way to offer a voice that
        will actually play.

        Returns `()` on any failure; the caller falls back to a browser-only picker rather
        than showing names that cannot be synthesised.
        """
        key = env_key(ENV_ELEVENLABS_KEY)
        if key is None:
            return ()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                response = await client.get(
                    f"{ELEVENLABS_BASE}/voices", headers={"xi-api-key": key}
                )
            if response.status_code >= 400:
                return ()
            voices = response.json().get("voices", [])
        except (httpx.HTTPError, ValueError):
            return ()

        return tuple(
            (str(v["voice_id"]), str(v.get("name") or v["voice_id"]))
            for v in voices
            if v.get("voice_id")
        )

    async def speak(self, text: str, *, voice_id: str | None = None) -> bytes:
        key = env_key(ENV_ELEVENLABS_KEY)
        if key is None:
            raise VoiceError("ELEVENLABS_API_KEY is not set")

        # Ordered fallback. The **account's own first voice** sits ahead of the stock id on
        # purpose: `DEFAULT_VOICE_ID` is a *library* voice, and a free-tier account is refused
        # those with `paid_plan_required` -- so a chain ending there fails for exactly the
        # accounts most likely to be running this. Asking the account costs one cached-ish
        # call and is the difference between working and silently degrading.
        #
        # `dict.fromkeys` dedupes while keeping order, so an id that appears twice is tried once.
        account_first = await self._first_account_voice()
        candidates = list(
            dict.fromkeys(
                v
                for v in (
                    voice_id,
                    env_key(ENV_ELEVENLABS_VOICE),
                    account_first,
                    DEFAULT_VOICE_ID,
                )
                if v
            )
        )

        last: Exception | None = None
        for voice in candidates:
            try:
                return await self._speak_with(key, voice, text)
            except QuotaExhausted:
                # Out of credit is an account fact, not a voice fact -- a second voice id
                # would fail identically, so stop and let the cascade drop a tier.
                raise
            except VoiceError as exc:
                last = exc
                continue
        raise VoiceError(f"every elevenlabs voice id failed; last: {last}")

    async def _first_account_voice(self) -> str | None:
        voices = await self.list_voices()
        return voices[0][0] if voices else None

    async def _speak_with(self, key: str, voice: str, text: str) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                response = await client.post(
                    f"{ELEVENLABS_BASE}/text-to-speech/{voice}",
                    headers={"xi-api-key": key, "accept": "audio/mpeg"},
                    json={
                        "text": text,
                        "model_id": ELEVENLABS_MODEL,
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                    },
                )
        except httpx.HTTPError as exc:  # network down, DNS, timeout
            raise VoiceError(f"elevenlabs request failed: {exc}") from exc

        if response.status_code >= 400:
            body = response.text[:400]
            if _is_quota(body) or response.status_code == 429:
                raise QuotaExhausted(f"elevenlabs quota exhausted: {body}")
            raise VoiceError(f"elevenlabs returned {response.status_code}: {body}")

        audio = response.content
        if not audio:
            # A 200 with an empty body would otherwise reach the browser as a silent <audio>
            # element -- indistinguishable from "the agent chose not to speak".
            raise VoiceError("elevenlabs returned an empty audio body")
        return audio


class WhisperTranscriber:
    """Speech in, tier 1. Groq first, OpenAI as the paid fallback within the same tier."""

    @property
    def name(self) -> str:
        return "whisper"

    def is_configured(self) -> bool:
        return env_key(ENV_GROQ_KEY) is not None or env_key(ENV_OPENAI_KEY) is not None

    async def transcribe(self, audio: bytes, *, mime_type: str) -> str:
        attempts: list[tuple[str, str, str]] = []
        groq = env_key(ENV_GROQ_KEY)
        if groq is not None:
            attempts.append((GROQ_TRANSCRIBE_URL, groq, GROQ_WHISPER_MODEL))
        openai = env_key(ENV_OPENAI_KEY)
        if openai is not None:
            attempts.append((OPENAI_TRANSCRIBE_URL, openai, OPENAI_WHISPER_MODEL))
        if not attempts:
            raise VoiceError("neither GROQ_API_KEY nor OPENAI_API_KEY is set")

        last: Exception | None = None
        for url, key, model in attempts:
            try:
                return await self._post(url, key, model, audio, mime_type)
            except VoiceError as exc:
                # Try the next provider in the same tier before letting the cascade drop a
                # whole tier -- a Groq rate limit should reach OpenAI, not the browser.
                last = exc
                continue
        raise VoiceError(f"every tier-1 transcriber failed; last: {last}")

    async def _post(self, url: str, key: str, model: str, audio: bytes, mime_type: str) -> str:
        files = {"file": (f"speech.{_extension(mime_type)}", audio, mime_type)}
        data: dict[str, Any] = {"model": model, "response_format": "json"}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                response = await client.post(
                    url, headers={"Authorization": f"Bearer {key}"}, files=files, data=data
                )
        except httpx.HTTPError as exc:
            raise VoiceError(f"transcription request failed: {exc}") from exc

        if response.status_code >= 400:
            body = response.text[:400]
            if _is_quota(body) or response.status_code == 429:
                raise QuotaExhausted(f"transcription quota exhausted: {body}")
            raise VoiceError(f"transcription returned {response.status_code}: {body}")
        try:
            text = str(response.json().get("text", "")).strip()
        except ValueError as exc:
            raise VoiceError("transcription response was not JSON") from exc
        if not text:
            raise VoiceError("transcription returned no text")
        return text


def _extension(mime_type: str) -> str:
    """Whisper's multipart endpoints key off the *filename* extension, not the part's
    content-type -- an upload named `speech.bin` is rejected as an unsupported format even
    when the mime type is correct."""
    return {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp4": "mp4",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
    }.get(mime_type.split(";")[0].strip().lower(), "webm")
