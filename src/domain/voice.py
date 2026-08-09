"""Voice as a three-tier cascade (PLAN-02 P16).

The brief says nothing about voice, so nothing here is a compliance question. The one real
constraint is **CONSTITUTION III.7**: the complete flow must run with the entire environment
unset. That never required the *best* path to be keyless -- only that *a* path always works.

So the good voice is the default and the fallback is automatic:

| Tier | Speech out | Speech in | Active when |
|---|---|---|---|
| `PROVIDER` | ElevenLabs | Groq Whisper | keys present |
| `BROWSER`  | `speechSynthesis` | `SpeechRecognition` | no keys, quota gone, provider error |
| `TEXT`     | nothing | typed input | no mic permission, unsupported browser |

**Selection happens per call, not per session.** A quota that runs out mid-demo drops to
`BROWSER` on the next utterance without a reload and without a dead button -- which is the
difference between a graceful degradation and a feature that visibly breaks in front of a
judge. `serving_tier` is recorded as a span attribute for exactly this reason: "the voice
sounded worse today" has to be a falsifiable claim.

Pure: no clock, no network, no environment reads (CONSTITUTION II.1). Everything this module
decides, it decides from arguments.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field


class VoiceTier(StrEnum):
    """Which layer actually served an utterance. Ordered best-first."""

    PROVIDER = "provider"
    BROWSER = "browser"
    TEXT = "text"

    @property
    def is_audible(self) -> bool:
        """Whether this tier produces or accepts sound at all."""
        return self is not VoiceTier.TEXT


#: Best to worst. The cascade walks this in order; nothing else defines the ordering, so a
#: new tier is one entry here rather than a comparison scattered across three call sites.
TIER_ORDER: Final[tuple[VoiceTier, ...]] = (
    VoiceTier.PROVIDER,
    VoiceTier.BROWSER,
    VoiceTier.TEXT,
)


def select_tier(*, provider_ready: bool, browser_ready: bool) -> VoiceTier:
    """The first tier that can actually serve this call.

    Pure and total: there is always an answer, because `TEXT` needs nothing. That totality is
    the point -- a voice feature with a "no tier available" branch is a voice feature that can
    leave the user with a dead microphone button and no explanation.
    """
    if provider_ready:
        return VoiceTier.PROVIDER
    if browser_ready:
        return VoiceTier.BROWSER
    return VoiceTier.TEXT


def next_tier(tier: VoiceTier) -> VoiceTier | None:
    """The tier to fall back to when `tier` fails mid-call. `None` past the floor."""
    index = TIER_ORDER.index(tier)
    return TIER_ORDER[index + 1] if index + 1 < len(TIER_ORDER) else None


class VoiceOption(BaseModel):
    """One selectable agent voice, for the picker (PLAN-02 P16's third control)."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    #: Which tier can actually play this voice. A `BROWSER` voice is whatever the OS ships;
    #: a `PROVIDER` voice is a specific ElevenLabs id.
    tier: VoiceTier


class VoiceCapabilities(BaseModel):
    """What the browser is told it can do, so the client never offers a control that would
    fail. Computed server-side because only the server knows which keys are set."""

    model_config = ConfigDict(frozen=True)

    #: The best tier available for speech *out* and speech *in*, independently -- a
    #: deployment can hold an ElevenLabs key and no Groq key, and saying "voice works" or
    #: "voice doesn't" for both together would be wrong in both directions.
    speak_tier: VoiceTier
    transcribe_tier: VoiceTier
    voices: tuple[VoiceOption, ...] = ()

    @property
    def any_provider(self) -> bool:
        return VoiceTier.PROVIDER in (self.speak_tier, self.transcribe_tier)


class Utterance(BaseModel):
    """A transcription result, plus which tier produced it.

    `text` is deliberately *not* auto-sent anywhere: PLAN-02 P16 requires the buyer to see and
    confirm what was heard before it becomes a turn. A mis-heard "no" that silently becomes a
    chat message is a much worse failure than one the user gets to correct.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    tier: VoiceTier
    #: Provider confidence when one is reported. `None` from tiers that do not report it --
    #: never defaulted to 1.0, which would claim certainty nothing measured.
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
