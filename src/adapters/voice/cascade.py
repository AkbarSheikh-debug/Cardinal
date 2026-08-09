"""The degradation cascade (PLAN-02 P16).

One object that answers two questions: *which tier can serve this call*, and *what happened
when it tried*. Everything above it (the API layer, the browser) reacts to the answer rather
than re-deriving it.

**Selection is per call.** A quota that empties mid-demo drops the next utterance to the
browser without a reload and without a dead button. Caching "we have a provider" at startup
is the obvious implementation and it is wrong: it turns a recoverable degradation into a
session that is broken until someone refreshes.

`DEMO_MODE` is its own path rather than a tier: it returns canned transcripts and declines to
synthesise, so `DEMO_MODE=true` with no keys still exercises the whole client flow (gate
16.2, CONSTITUTION III.7). The demo transcripts cycle **per session**, not from one global
counter -- two browsers open at once would otherwise interleave and each see half a script.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Final

from src.adapters.voice.protocol import (
    SpeechSynthesizer,
    SpeechTranscriber,
    VoiceError,
)
from src.adapters.voice.providers import ElevenLabsSynthesizer, WhisperTranscriber
from src.domain.voice import Utterance, VoiceCapabilities, VoiceOption, VoiceTier, select_tier

#: Under 500 bytes is a press-and-release with no speech in it. Rejecting locally saves a
#: provider call and, more importantly, saves the user a confusing empty transcript.
MIN_AUDIO_BYTES: Final[int] = 500

#: What `DEMO_MODE` hears. Buyer-shaped, so the scripted flow reaches a real
#: `RequirementProfile` rather than transcripts about something else entirely.
DEMO_TRANSCRIPTS: Final[tuple[str, ...]] = (
    "I'm looking for a family SUV, budget around thirty thousand euros.",
    "Mostly motorway commuting, about twenty thousand kilometres a year.",
    "I'd rather buy than rent if it works out cheaper over three years.",
    "Can you show me what the total cost looks like over that period?",
    "That second one looks right. Can I see who's selling it?",
)

#: The voices the picker offers on tier 1. Stock ElevenLabs ids -- a deployment with its own
#: cloned voices overrides the default via `ELEVENLABS_VOICE_ID` and can extend this list.
PROVIDER_VOICES: Final[tuple[VoiceOption, ...]] = (
    VoiceOption(id="21m00Tcm4TlvDq8ikWAM", label="Rachel — warm, neutral", tier=VoiceTier.PROVIDER),
    VoiceOption(id="pNInz6obpgDQGcFmaJgB", label="Adam — deep, steady", tier=VoiceTier.PROVIDER),
    VoiceOption(id="EXAVITQu4vr4xnSDxMaL", label="Bella — bright, quick", tier=VoiceTier.PROVIDER),
)

#: Tier 2 has exactly one entry: the browser picks the actual voice from what the OS ships, so
#: naming specific ones here would promise something we cannot deliver cross-platform.
BROWSER_VOICE: Final[VoiceOption] = VoiceOption(
    id="browser-default", label="System voice", tier=VoiceTier.BROWSER
)

logger = logging.getLogger(__name__)

DEMO_MODE_ENV = "DEMO_MODE"


def demo_mode() -> bool:
    return os.environ.get(DEMO_MODE_ENV, "").lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class SpokenAudio:
    audio: bytes
    mime_type: str
    tier: VoiceTier


class VoiceCascade:
    """Speech in and out, with the tier decided per call.

    Both providers are injectable so a test can hand in a stub -- which is how gate 16.3
    proves tier 1 is *selected* without needing a live ElevenLabs key, and how gate 16.4
    proves a mid-session quota error degrades without waiting for a real account to run dry.
    """

    def __init__(
        self,
        *,
        synthesizer: SpeechSynthesizer | None = None,
        transcriber: SpeechTranscriber | None = None,
    ) -> None:
        self._synth = synthesizer if synthesizer is not None else ElevenLabsSynthesizer()
        self._stt = transcriber if transcriber is not None else WhisperTranscriber()
        #: Per-session demo cursor. Keyed rather than global -- see the module docstring.
        self._demo_turns: dict[str, int] = {}

    # -- capability reporting ---------------------------------------------------------

    async def capabilities(self, *, browser_ready: bool = True) -> VoiceCapabilities:
        """What the client is allowed to offer. `browser_ready` is the browser's own claim
        about Web Speech support, which only it can know.

        Async because the voice list comes from the **account**, not from a constant. The
        first version hardcoded well-known library voice ids and every call failed with
        `paid_plan_required` on a free tier while this method still reported tier 1 -- a
        picker full of names that could not be synthesised.
        """
        speak_provider = self._synth.is_configured() and not demo_mode()
        stt_provider = self._stt.is_configured() and not demo_mode()

        voices: tuple[VoiceOption, ...] = (BROWSER_VOICE,)
        if speak_provider:
            account_voices = await self._account_voices()
            # No usable account voices means the provider is configured but cannot serve this
            # account -- offer the browser rather than a menu that 402s on every click.
            voices = (*account_voices, BROWSER_VOICE) if account_voices else (BROWSER_VOICE,)
        return VoiceCapabilities(
            speak_tier=select_tier(provider_ready=speak_provider, browser_ready=browser_ready),
            transcribe_tier=select_tier(provider_ready=stt_provider, browser_ready=browser_ready),
            voices=voices,
        )

    async def _account_voices(self) -> tuple[VoiceOption, ...]:
        """The voices this ElevenLabs account may actually use, when the provider can say."""
        lister = getattr(self._synth, "list_voices", None)
        if lister is None:
            return PROVIDER_VOICES  # a stub synthesiser in a test; keep the old behaviour
        try:
            pairs = await lister()
        except Exception:  # never let a picker lookup break the whole capabilities call
            return ()
        return tuple(
            VoiceOption(id=voice_id, label=name, tier=VoiceTier.PROVIDER)
            for voice_id, name in pairs
        )

    # -- speech out -------------------------------------------------------------------

    async def speak(self, text: str, *, voice_id: str | None = None) -> SpokenAudio | None:
        """Audio when tier 1 can serve it, `None` when the caller should use the browser.

        `None` rather than an exception, because "the browser should say this instead" is an
        ordinary outcome, not a failure -- and a route that raised here would push the caller
        into treating a normal degradation as an error state.
        """
        if demo_mode() or not self._synth.is_configured():
            return None
        try:
            audio = await self._synth.speak(text, voice_id=voice_id)
        except VoiceError as exc:
            # Covers quota exhaustion and provider outages alike. Both mean the same thing to
            # the caller: this utterance is the browser's job.
            #
            # Logged, not swallowed. A silent degradation is indistinguishable from "no key
            # configured" from the outside -- which is exactly the failure that wasted a
            # debugging session: capabilities reported `provider` while every call quietly
            # fell to the browser, and nothing anywhere said why. `VoiceError` messages are
            # constructed to carry a provider error *code*, never a credential.
            logger.warning("tier-1 speech-out failed, falling back to the browser: %s", exc)
            return None
        return SpokenAudio(audio=audio, mime_type="audio/mpeg", tier=VoiceTier.PROVIDER)

    # -- speech in --------------------------------------------------------------------

    async def transcribe(
        self, audio: bytes, *, mime_type: str, session_id: str = "unbound"
    ) -> Utterance | None:
        """Text when tier 1 can serve it, `None` when the caller should use the browser."""
        if demo_mode():
            turn = self._demo_turns.get(session_id, 0)
            self._demo_turns[session_id] = turn + 1
            return Utterance(
                text=DEMO_TRANSCRIPTS[turn % len(DEMO_TRANSCRIPTS)], tier=VoiceTier.BROWSER
            )
        if not self._stt.is_configured():
            return None
        if len(audio) < MIN_AUDIO_BYTES:
            # Not a provider decision -- there is no speech in this many bytes, and asking a
            # provider produces an empty transcript that reads to the user as "it ignored me".
            raise VoiceError("that recording was too short to contain speech")
        try:
            text = await self._stt.transcribe(audio, mime_type=mime_type)
        except VoiceError as exc:
            logger.warning("tier-1 speech-in failed, falling back to the browser: %s", exc)
            return None
        return Utterance(text=text, tier=VoiceTier.PROVIDER)
