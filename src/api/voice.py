"""Voice transport -- PLAN-02 P16. Routes only; every decision lives in the cascade.

Three routes, and the shape of the first two is the whole design:

- `POST /voice/speak` returns **audio** when tier 1 served it, and **204 No Content** when the
  browser should speak instead. Not a 4xx/5xx: falling back is an ordinary outcome, and a
  route that errors on it would make the client treat a working degradation as a broken
  feature (and log it as one).
- `POST /voice/transcribe` answers the same way -- a transcript, or 204 meaning "use Web
  Speech".

Every response carries `X-Voice-Tier`, and every call opens a span with the same value
(gate 16.9). Without that, "the voice sounded worse today" is unfalsifiable.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile

from src.adapters.voice import VoiceCascade, VoiceError
from src.agent.tracing import get_tracer
from src.domain.voice import VoiceTier

router = APIRouter()

#: Echoed on every voice response and recorded on every span. One name, so a header a
#: developer reads in devtools and an attribute they read in a trace are the same string.
TIER_HEADER = "X-Voice-Tier"

#: A single utterance. Long enough for a paragraph of agent reply, short enough that a runaway
#: prompt cannot turn into a minute of synthesis (and a minute of provider credit).
MAX_SPEAK_CHARS = 1_200


def cascade(request: Request) -> VoiceCascade:
    engine: VoiceCascade = request.app.state.voice
    return engine


@router.get("/voice/capabilities")
async def capabilities(request: Request, browser: bool = True) -> dict[str, Any]:
    """What this deployment can actually offer.

    `browser` is the client telling us whether Web Speech exists in *its* runtime -- the
    server cannot know, and assuming it does is how Safari users get offered a control that
    silently does nothing.
    """
    caps = await cascade(request).capabilities(browser_ready=browser)
    return {
        "speak_tier": caps.speak_tier.value,
        "transcribe_tier": caps.transcribe_tier.value,
        "voices": [{"id": v.id, "label": v.label, "tier": v.tier.value} for v in caps.voices],
    }


@router.post("/voice/speak")
async def speak(request: Request, response: Response) -> Response:
    body = await request.json()
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=422, detail="text is required")
    if len(text) > MAX_SPEAK_CHARS:
        text = text[:MAX_SPEAK_CHARS]
    voice_id = body.get("voice_id") or None

    with get_tracer().start_as_current_span("voice.speak") as span:
        span.set_attribute("voice.chars", len(text))
        spoken = await cascade(request).speak(text, voice_id=str(voice_id) if voice_id else None)
        tier = spoken.tier if spoken is not None else VoiceTier.BROWSER
        span.set_attribute("voice.tier", tier.value)

    if spoken is None:
        # 204: nothing to play, and the client already knows what to do about it.
        return Response(status_code=204, headers={TIER_HEADER: VoiceTier.BROWSER.value})
    return Response(
        content=spoken.audio,
        media_type=spoken.mime_type,
        headers={TIER_HEADER: spoken.tier.value, "Cache-Control": "no-store"},
    )


#: Module-level singletons rather than inline `File(...)`/`Form(...)` calls in the signature.
#: FastAPI's documented idiom is the inline form, but ruff's B008 bans a call in a default
#: argument repo-wide and suppressing it here would weaken a rule that is right everywhere
#: else. Binding them once is the same object with none of the ambiguity.
_AUDIO_FILE = File(...)
_SESSION_FORM = Form(default="unbound")


@router.post("/voice/transcribe")
async def transcribe(
    request: Request,
    file: UploadFile = _AUDIO_FILE,
    session_id: str = _SESSION_FORM,
) -> Response:
    audio = await file.read()
    mime_type = file.content_type or "audio/webm"

    with get_tracer().start_as_current_span("voice.transcribe") as span:
        span.set_attribute("voice.bytes", len(audio))
        try:
            utterance = await cascade(request).transcribe(
                audio, mime_type=mime_type, session_id=session_id
            )
        except VoiceError as exc:
            # Too-short audio is the caller's problem to fix (press and hold for longer), so
            # it is a 422 rather than a silent fallback -- the browser would transcribe the
            # same silence to the same nothing.
            span.set_attribute("voice.tier", VoiceTier.TEXT.value)
            raise HTTPException(status_code=422, detail=str(exc)) from None
        tier = utterance.tier if utterance is not None else VoiceTier.BROWSER
        span.set_attribute("voice.tier", tier.value)

    if utterance is None:
        return Response(status_code=204, headers={TIER_HEADER: VoiceTier.BROWSER.value})
    # The transcript is returned for the user to *confirm*, never auto-sent (PLAN-02 P16).
    return Response(
        content=utterance.model_dump_json(),
        media_type="application/json",
        headers={TIER_HEADER: utterance.tier.value},
    )
