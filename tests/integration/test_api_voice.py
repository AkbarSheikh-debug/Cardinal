"""`/voice/*` through the real FastAPI app -- PLAN-02 P16.

The shape under test is the 204: tier 1 declining is an ordinary outcome the client handles,
not an error. A route that 5xx'd there would make a working degradation look broken in every
log and every dashboard.
"""

from __future__ import annotations

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.adapters.voice.cascade import DEMO_TRANSCRIPTS, MIN_AUDIO_BYTES, VoiceCascade
from src.api.main import app
from src.api.voice import TIER_HEADER

AUDIO = b"x" * (MIN_AUDIO_BYTES + 1)

VOICE_ENV = (
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "DEMO_MODE",
)


@pytest.fixture(autouse=True)
def _no_voice_keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every test here runs with the environment scrubbed, which is both the judge's machine
    and CONSTITUTION III.7's requirement."""
    for name in VOICE_ENV:
        monkeypatch.delenv(name, raising=False)
    yield


def _upload(audio: bytes = AUDIO) -> dict[str, object]:
    return {"file": ("speech.webm", io.BytesIO(audio), "audio/webm")}


def test_capabilities_report_browser_tiers_with_no_keys() -> None:
    with TestClient(app) as client:
        body = client.get("/voice/capabilities").json()
        assert body["speak_tier"] == "browser"
        assert body["transcribe_tier"] == "browser"
        # Exactly one voice: the system one. Offering ElevenLabs names with no key would be
        # a picker whose entries silently do nothing.
        assert [v["tier"] for v in body["voices"]] == ["browser"]


def test_a_client_without_web_speech_is_told_text_only() -> None:
    with TestClient(app) as client:
        body = client.get("/voice/capabilities?browser=false").json()
        assert body["speak_tier"] == "text"
        assert body["transcribe_tier"] == "text"


def test_speak_returns_204_and_names_the_tier_when_no_provider() -> None:
    with TestClient(app) as client:
        response = client.post("/voice/speak", json={"text": "hello"})
        assert response.status_code == 204
        assert response.headers[TIER_HEADER] == "browser"


def test_speak_requires_text() -> None:
    with TestClient(app) as client:
        assert client.post("/voice/speak", json={"text": "   "}).status_code == 422


def test_transcribe_returns_204_when_no_provider() -> None:
    with TestClient(app) as client:
        response = client.post("/voice/transcribe", files=_upload())
        assert response.status_code == 204
        assert response.headers[TIER_HEADER] == "browser"


def test_speak_serves_audio_when_a_provider_is_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gate 16.3's mechanism: a stub provider proves tier 1 is *selected* without needing a
    funded ElevenLabs account for the test to run at all."""

    class Synth:
        name = "stub"

        def is_configured(self) -> bool:
            return True

        async def speak(self, text: str, *, voice_id: str | None = None) -> bytes:
            return b"ID3fake-mp3"

    with TestClient(app) as client:
        app.state.voice = VoiceCascade(synthesizer=Synth())
        response = client.post("/voice/speak", json={"text": "hello"})
        assert response.status_code == 200
        assert response.headers[TIER_HEADER] == "provider"
        assert response.headers["content-type"].startswith("audio/mpeg")
        assert response.content == b"ID3fake-mp3"
        # Audio of a specific user's conversation must not sit in a shared cache.
        assert response.headers["cache-control"] == "no-store"


def test_too_short_audio_is_422_not_a_silent_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class Stt:
        name = "stub"

        def is_configured(self) -> bool:
            return True

        async def transcribe(self, audio: bytes, *, mime_type: str) -> str:
            raise AssertionError("a too-short clip reached the provider")

    with TestClient(app) as client:
        app.state.voice = VoiceCascade(transcriber=Stt())
        response = client.post("/voice/transcribe", files=_upload(b"tiny"))
        assert response.status_code == 422


def test_demo_mode_returns_a_canned_transcript_with_no_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gate 16.2 / CONSTITUTION III.7: a voice turn completes with the environment unset."""
    monkeypatch.setenv("DEMO_MODE", "true")
    with TestClient(app) as client:
        app.state.voice = VoiceCascade()
        response = client.post("/voice/transcribe", files=_upload(), data={"session_id": "demo-1"})
        assert response.status_code == 200
        body = response.json()
        assert body["text"] == DEMO_TRANSCRIPTS[0]
        assert body["tier"] == "browser"


def test_the_transcript_is_returned_not_sent_as_a_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """No auto-send (PLAN-02 P16): transcribing must not create a chat turn as a side effect.
    Asserted by checking the session's own message list stays empty."""
    monkeypatch.setenv("DEMO_MODE", "true")
    with TestClient(app) as client:
        app.state.voice = VoiceCascade()
        client.post("/voice/transcribe", files=_upload(), data={"session_id": "quiet"})
        recorded = app.state.orchestrator.actions_for("quiet")
        assert recorded == []
