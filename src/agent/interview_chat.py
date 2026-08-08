"""Model-selectable INTERVIEW-phase chat (D-056): one call per turn against whichever provider
the session picked, producing both the assistant's reply and the same kind of `SlotUpdate`s a
live Claude session's `ModelSlotExtractor` would produce -- folded through `process_turn`
unchanged, so phase transitions are byte-identical to every other path (`DemoSlotExtractor`,
`ModelSlotExtractor`) regardless of which model asked the question.

RESEARCH and everything after it still runs through `CardinalOrchestrator`'s Claude Agent SDK
session, tools and guardrails untouched -- this module never constructs a tool, never sees
`booking-mcp`, and stops mattering the moment `Phase` advances past INTERVIEW.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

from src.agent.extraction import SlotExtractor, SlotUpdate
from src.agent.interview import process_turn
from src.agent.model_catalog import find as find_model
from src.agent.phase_machine import SessionState
from src.agent.prompts import load_prompt
from src.agent.providers import chat


@dataclass(frozen=True)
class InterviewTurn:
    state: SessionState
    reply: str


class _PreparsedExtractor:
    """Adapts a list of updates this module already fetched to the `SlotExtractor` protocol,
    so `interview_turn` can hand off to `process_turn` and get the identical phase-transition
    logic every other extractor gets, instead of a second copy of it.
    """

    def __init__(self, updates: tuple[SlotUpdate, ...]) -> None:
        self._updates = updates

    async def extract(self, utterance: str, profile: object) -> tuple[SlotUpdate, ...]:
        del utterance, profile
        return self._updates


#: Reasoning models on Groq/OpenRouter (Qwen, DeepSeek, gpt-oss) emit a `<think>...</think>`
#: block ahead of the actual answer -- verified live against `groq/qwen/qwen3.6-27b` (D-056),
#: same failure `D:\Interview Agent`'s `llm_router.py` already documents and strips. Left in,
#: it's both wasted tokens the JSON never gets to and, if truncated by `max_tokens`, no JSON
#: at all -- exactly what a naive first attempt against this model produced.
_CLOSED_THINK_RE = re.compile(r"<\s*think\b[^>]*>.*?<\s*/\s*think\s*>", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK_RE = re.compile(r"<\s*think\b[^>]*>.*\Z", re.DOTALL | re.IGNORECASE)


def _strip_reasoning(text: str) -> str:
    stripped = _CLOSED_THINK_RE.sub("", text)
    stripped = _UNCLOSED_THINK_RE.sub("", stripped)
    return stripped.strip()


def _parse_reply_and_updates(text: str) -> tuple[str, tuple[SlotUpdate, ...]]:
    """Cheaper/weaker models than Claude are exactly what this path exists to support, so
    parsing is defensive: a response that isn't the JSON object the prompt asked for still
    becomes a visible reply (the raw text) with no slot updates, rather than a dropped turn.
    """
    text = _strip_reasoning(text)
    try:
        parsed = json.loads(_strip_code_fence(text))
    except (json.JSONDecodeError, TypeError):
        return text.strip(), ()
    if not isinstance(parsed, dict):
        return text.strip(), ()
    reply = parsed.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        reply = text.strip()
    updates: list[SlotUpdate] = []
    for entry in parsed.get("updates") or []:
        if not isinstance(entry, dict):
            continue
        field = entry.get("field")
        if not isinstance(field, str):
            continue
        try:
            confidence = float(entry.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        updates.append(
            SlotUpdate(field, entry.get("value"), confidence, bool(entry.get("locked", False)))
        )
    return reply, tuple(updates)


def _strip_code_fence(text: str) -> str:
    # Weaker models routinely wrap JSON in ```json ... ``` despite being told not to.
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped.rsplit("```", 1)[0]
    return stripped.strip()


def _payload(state: SessionState, utterance: str, *, today: date) -> list[dict[str, str]]:
    # `SessionState` carries no transcript today -- the Claude path leans on the SDK's own
    # session resume for conversational memory (D-052); the profile gathered so far plus this
    # turn's utterance is enough context for one focused follow-up, which is this path's whole
    # job. A real transcript would let it reference earlier turns verbatim, which it can't yet.
    #
    # `today` is passed in rather than read here so the payload stays a pure function of its
    # arguments and a test can pin the date. Without it the model cannot resolve "in 2 days"
    # into the ISO `target_date` the prompt demands, and a reasoning model does not fail
    # cleanly on that -- it deliberates about placeholder dates until `max_tokens` runs out
    # mid-`<think>`, leaving no JSON and no reply at all (D-058).
    profile_json = json.dumps(state.profile.model_dump(mode="json"), default=str)
    return [
        {"role": "system", "content": load_prompt("interview_chat")},
        {
            "role": "user",
            "content": f"Today is {today.isoformat()}.\n\n"
            f"Known so far (RequirementProfile JSON): {profile_json}\n\n"
            f"User just said: {utterance}",
        },
    ]


def handoff_summary(state: SessionState) -> str:
    """A short, plain-text account of what an alternate-model INTERVIEW gathered, for
    `src/api/main.py` to prepend to the first turn a live Claude session ever sees after a
    hand-off (D-056's `needs_handoff_priming`) -- without it, that session starts blank and
    has no memory of an interview it never actually ran.
    """
    profile = state.profile
    parts: list[str] = []
    if profile.goal.value is not None:
        parts.append(f"goal: {profile.goal.value.value}")
    if profile.category.value is not None:
        parts.append(f"category: {', '.join(c.value for c in profile.category.value)}")
    if profile.budget.value is not None:
        parts.append(f"budget: {profile.budget.value}")
    if profile.target_date.value is not None:
        parts.append(f"target date: {profile.target_date.value.isoformat()}")
    if profile.use_case.value is not None:
        parts.append(f"use case: {profile.use_case.value}")
    summary = "; ".join(parts) if parts else "none captured"
    return (
        "[The INTERVIEW phase is already complete, gathered by a different model -- not you, "
        "and not in this conversation. Do not re-ask the interview questions. "
        f"Requirements gathered: {summary}. Proceed directly with RESEARCH.] "
    )


async def interview_turn(
    state: SessionState, utterance: str, model_id: str, *, today: date | None = None
) -> InterviewTurn:
    """One INTERVIEW-phase turn on the given `provider/model` id (never the `CLAUDE_MODEL_ID`
    sentinel -- callers branch on that before reaching here, per `model_catalog`'s docstring).

    `today` defaults to the real current date and exists so a test can pin it; the model needs
    it to resolve "in 2 days" into the ISO `target_date` the prompt asks for (D-058).
    """
    info = find_model(model_id)
    # Generous relative to a plain chat model's needs: a reasoning model (Qwen, DeepSeek,
    # gpt-oss) spends a few hundred tokens on <think> before ever reaching the JSON, and a
    # truncated <think> block with no JSON after it is a dropped turn (verified live, D-056).
    # `reasoning_format="hidden"` is the structural fix on the providers that honour it -- the
    # `max_tokens` headroom and `_strip_reasoning` both stay for the ones that don't (D-058).
    raw = await chat(
        model_id,
        _payload(state, utterance, today=today or date.today()),
        temperature=0.4,
        max_tokens=2000,
        reasoning_format="hidden" if info and info["reasoning"] else None,
    )
    reply, updates = _parse_reply_and_updates(raw)
    if not reply:
        # An unclosed <think> block with nothing after it (max_tokens exhausted mid-thought)
        # parses down to an empty string -- a blank chat bubble reads as broken the same way
        # D-052/D-053/D-054's silent failures did. Never show the user nothing.
        reply = "Sorry, could you say that again?"
    extractor: SlotExtractor = _PreparsedExtractor(updates)
    new_state = await process_turn(state, utterance, extractor)
    return InterviewTurn(state=new_state, reply=reply)
