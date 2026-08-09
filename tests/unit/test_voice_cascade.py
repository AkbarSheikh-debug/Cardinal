"""The voice cascade -- PLAN-02 P16.

The tests that matter are the degradation ones: tier 1 selected when it can serve, tier 2 the
moment it cannot, and *per call* rather than per session. Stub providers throughout -- gate
16.3's own reasoning: proving the cascade selects tier 1 must not require a live ElevenLabs
key, or the criterion could only ever run on a machine with a funded account.
"""

from __future__ import annotations

import pytest

from src.adapters.voice.cascade import DEMO_TRANSCRIPTS, MIN_AUDIO_BYTES, VoiceCascade
from src.adapters.voice.protocol import QuotaExhausted, VoiceError, env_key
from src.domain.voice import TIER_ORDER, VoiceTier, next_tier, select_tier

AUDIO = b"x" * (MIN_AUDIO_BYTES + 1)


class StubSynth:
    """Configurable tier-1 speech-out."""

    def __init__(self, *, configured: bool = True, fails: Exception | None = None) -> None:
        self._configured = configured
        self._fails = fails
        self.calls = 0

    @property
    def name(self) -> str:
        return "stub-synth"

    def is_configured(self) -> bool:
        return self._configured

    async def speak(self, text: str, *, voice_id: str | None = None) -> bytes:
        self.calls += 1
        if self._fails is not None:
            raise self._fails
        return b"ID3-audio-bytes"


class StubStt:
    def __init__(self, *, configured: bool = True, fails: Exception | None = None) -> None:
        self._configured = configured
        self._fails = fails
        self.calls = 0

    @property
    def name(self) -> str:
        return "stub-stt"

    def is_configured(self) -> bool:
        return self._configured

    async def transcribe(self, audio: bytes, *, mime_type: str) -> str:
        self.calls += 1
        if self._fails is not None:
            raise self._fails
        return "a family suv under thirty thousand"


@pytest.fixture(autouse=True)
def _no_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most tests here are about the *live* cascade; DEMO_MODE has its own tests below."""
    monkeypatch.delenv("DEMO_MODE", raising=False)


# -- pure tier selection -------------------------------------------------------------


def test_provider_wins_when_available() -> None:
    assert select_tier(provider_ready=True, browser_ready=True) is VoiceTier.PROVIDER


def test_browser_serves_when_no_provider() -> None:
    assert select_tier(provider_ready=False, browser_ready=True) is VoiceTier.BROWSER


def test_text_is_the_floor_and_always_reachable() -> None:
    """Totality is the point: a "no tier available" branch is how a user ends up with a dead
    microphone button and no explanation."""
    assert select_tier(provider_ready=False, browser_ready=False) is VoiceTier.TEXT


def test_tier_order_is_best_first_and_terminates() -> None:
    assert TIER_ORDER[0] is VoiceTier.PROVIDER
    assert next_tier(VoiceTier.PROVIDER) is VoiceTier.BROWSER
    assert next_tier(VoiceTier.BROWSER) is VoiceTier.TEXT
    assert next_tier(VoiceTier.TEXT) is None


def test_only_text_is_inaudible() -> None:
    assert VoiceTier.PROVIDER.is_audible and VoiceTier.BROWSER.is_audible
    assert not VoiceTier.TEXT.is_audible


# -- speech out ----------------------------------------------------------------------


async def test_a_configured_provider_serves_tier_one() -> None:
    cascade = VoiceCascade(synthesizer=StubSynth(), transcriber=StubStt())
    spoken = await cascade.speak("hello")
    assert spoken is not None
    assert spoken.tier is VoiceTier.PROVIDER
    assert spoken.mime_type == "audio/mpeg"


async def test_no_provider_configured_returns_none_for_the_browser() -> None:
    cascade = VoiceCascade(synthesizer=StubSynth(configured=False), transcriber=StubStt())
    assert await cascade.speak("hello") is None


async def test_quota_exhaustion_degrades_rather_than_raising() -> None:
    """Gate 16.4's mechanism. A quota that empties mid-demo must not surface as an error."""
    cascade = VoiceCascade(
        synthesizer=StubSynth(fails=QuotaExhausted("out of credit")), transcriber=StubStt()
    )
    assert await cascade.speak("hello") is None


async def test_a_provider_outage_degrades_the_same_way() -> None:
    cascade = VoiceCascade(synthesizer=StubSynth(fails=VoiceError("502")), transcriber=StubStt())
    assert await cascade.speak("hello") is None


async def test_tier_is_chosen_per_call_not_cached() -> None:
    """The whole point of the cascade. A synth that works, then fails, then works again must
    serve tier 1, tier 2, tier 1 -- not latch to the browser after the first failure."""

    class Flaky(StubSynth):
        def __init__(self) -> None:
            super().__init__()
            self.n = 0

        async def speak(self, text: str, *, voice_id: str | None = None) -> bytes:
            self.n += 1
            if self.n == 2:
                raise QuotaExhausted("transient")
            return b"audio"

    cascade = VoiceCascade(synthesizer=Flaky(), transcriber=StubStt())
    first = await cascade.speak("one")
    second = await cascade.speak("two")
    third = await cascade.speak("three")

    assert first is not None and first.tier is VoiceTier.PROVIDER
    assert second is None  # browser serves this one
    assert third is not None and third.tier is VoiceTier.PROVIDER


# -- speech in -----------------------------------------------------------------------


async def test_a_configured_transcriber_serves_tier_one() -> None:
    cascade = VoiceCascade(synthesizer=StubSynth(), transcriber=StubStt())
    utterance = await cascade.transcribe(AUDIO, mime_type="audio/webm")
    assert utterance is not None
    assert utterance.tier is VoiceTier.PROVIDER
    assert "suv" in utterance.text


async def test_an_unconfigured_transcriber_hands_off_to_the_browser() -> None:
    cascade = VoiceCascade(synthesizer=StubSynth(), transcriber=StubStt(configured=False))
    assert await cascade.transcribe(AUDIO, mime_type="audio/webm") is None


async def test_audio_too_short_is_refused_before_a_provider_call() -> None:
    """A press-and-release with no speech in it. Asking a provider costs a call and returns
    an empty transcript, which reads to the user as "it ignored me"."""
    stt = StubStt()
    cascade = VoiceCascade(synthesizer=StubSynth(), transcriber=stt)
    with pytest.raises(VoiceError):
        await cascade.transcribe(b"tiny", mime_type="audio/webm")
    assert stt.calls == 0, "a too-short clip still reached the provider"


async def test_a_transcriber_failure_degrades_to_the_browser() -> None:
    cascade = VoiceCascade(synthesizer=StubSynth(), transcriber=StubStt(fails=VoiceError("nope")))
    assert await cascade.transcribe(AUDIO, mime_type="audio/webm") is None


# -- DEMO_MODE (gate 16.2) -----------------------------------------------------------


async def test_demo_mode_transcribes_without_any_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    cascade = VoiceCascade(
        synthesizer=StubSynth(configured=False), transcriber=StubStt(configured=False)
    )
    utterance = await cascade.transcribe(b"", mime_type="audio/webm", session_id="s1")
    assert utterance is not None
    assert utterance.text == DEMO_TRANSCRIPTS[0]


async def test_demo_transcripts_advance_per_session_not_globally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two browsers open at once must each see the script from the top -- a single global
    cursor would interleave them and give each half a conversation."""
    monkeypatch.setenv("DEMO_MODE", "true")
    cascade = VoiceCascade(synthesizer=StubSynth(), transcriber=StubStt())

    a1 = await cascade.transcribe(b"", mime_type="audio/webm", session_id="alice")
    b1 = await cascade.transcribe(b"", mime_type="audio/webm", session_id="bob")
    a2 = await cascade.transcribe(b"", mime_type="audio/webm", session_id="alice")

    assert a1 is not None and b1 is not None and a2 is not None
    assert a1.text == DEMO_TRANSCRIPTS[0]
    assert b1.text == DEMO_TRANSCRIPTS[0], "bob inherited alice's position in the script"
    assert a2.text == DEMO_TRANSCRIPTS[1]


async def test_demo_mode_declines_to_synthesise_so_the_browser_speaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    cascade = VoiceCascade(synthesizer=StubSynth(), transcriber=StubStt())
    assert await cascade.speak("hello") is None


async def test_demo_mode_reports_browser_tiers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    caps = await VoiceCascade(synthesizer=StubSynth(), transcriber=StubStt()).capabilities()
    assert caps.speak_tier is VoiceTier.BROWSER
    assert caps.transcribe_tier is VoiceTier.BROWSER
    assert not caps.any_provider


# -- capabilities --------------------------------------------------------------------


async def test_capabilities_report_each_direction_independently() -> None:
    """A deployment can hold an ElevenLabs key and no Groq key. Saying "voice works" or
    "voice doesn't" for both together would be wrong in both directions."""
    caps = await VoiceCascade(
        synthesizer=StubSynth(), transcriber=StubStt(configured=False)
    ).capabilities()
    assert caps.speak_tier is VoiceTier.PROVIDER
    assert caps.transcribe_tier is VoiceTier.BROWSER


async def test_a_browserless_client_falls_to_text() -> None:
    caps = await VoiceCascade(
        synthesizer=StubSynth(configured=False), transcriber=StubStt(configured=False)
    ).capabilities(browser_ready=False)
    assert caps.speak_tier is VoiceTier.TEXT
    assert caps.transcribe_tier is VoiceTier.TEXT


async def test_the_picker_only_offers_provider_voices_when_a_provider_exists() -> None:
    with_provider = await VoiceCascade(
        synthesizer=StubSynth(), transcriber=StubStt()
    ).capabilities()
    without = await VoiceCascade(
        synthesizer=StubSynth(configured=False), transcriber=StubStt()
    ).capabilities()

    assert any(v.tier is VoiceTier.PROVIDER for v in with_provider.voices)
    assert all(v.tier is VoiceTier.BROWSER for v in without.voices)
    assert len(without.voices) == 1


# -- credential handling -------------------------------------------------------------


def test_an_empty_env_var_counts_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """`ELEVENLABS_API_KEY=` in a .env file produces an empty string. Treating that as
    configured is how a provider gets called with an empty bearer token."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    assert env_key("ELEVENLABS_API_KEY") is None
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-real")
    assert env_key("ELEVENLABS_API_KEY") == "sk-real"
