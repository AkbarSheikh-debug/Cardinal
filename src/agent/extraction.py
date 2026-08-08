"""Slot extraction (PHASE-3 §5): a separate, tiny call per user turn, not something the
orchestrator does inline.

Two implementations of one `SlotExtractor` protocol. `ModelSlotExtractor` is the real path --
`claude-haiku-4-5`, 5x cheaper than the orchestrator's model and run every turn, which is
exactly the high-frequency/narrow-task combination PLAN-00 §6.7 calls out. `DemoSlotExtractor`
is deterministic and network-free: `DEMO_MODE=true` must complete the whole flow with no API
key present (CONSTITUTION III.7), and the interview is the phase that runs a model call on
literally every turn, so it is the phase demo mode has the least room to fake believably --
a regex-and-keyword parser stands in for haiku rather than a canned transcript, because the
personas' utterances are meant to be varied inputs, not a fixed script to replay.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from src.domain.enums import OfferType, VehicleCategory
from src.domain.money import Money
from src.domain.profile import RequirementProfile


@dataclass(frozen=True)
class SlotUpdate:
    field: str
    value: object
    confidence: float
    locked: bool = False


class SlotExtractor(Protocol):
    async def extract(
        self, utterance: str, profile: RequirementProfile
    ) -> tuple[SlotUpdate, ...]: ...


def apply_updates(
    profile: RequirementProfile, updates: tuple[SlotUpdate, ...], *, turn: int
) -> RequirementProfile:
    """Fold extracted updates into a profile. `Slot.fill` already refuses to overwrite a
    locked slot with an unlocked one (`src/domain/profile.py`), so a later inference can
    never quietly walk back an earlier direct statement.
    """
    data = profile.model_dump()
    for update in updates:
        if update.field not in RequirementProfile.model_fields:
            continue
        current = getattr(profile, update.field)
        filled = current.fill(
            update.value, confidence=update.confidence, turn=turn, locked=update.locked
        )
        data[update.field] = filled.model_dump()
    return RequirementProfile.model_validate(data)


# -- Demo / offline extractor -------------------------------------------------------------

#: Matching is first-pattern-wins, so the explicitly-undecided phrasings have to be checked
#: *before* the bare rent/buy keywords they contain -- ordered after them (as they originally
#: were), `not sure whether to rent or buy` could never reach BOTH, because "rent" matched one
#: line earlier. Kept narrow and two-sided ("rent or buy", "not sure ... rent") so an
#: incidental "both" ("both my wife and I want to rent") doesn't hijack a clear statement.
_UNDECIDED_PATTERN = re.compile(
    r"\b(?:not sure|undecided|can't decide|cannot decide|torn)\b.*\b(?:rent|buy|lease)"
    r"|\b(?:rent\w*|lease\w*)\s+or\s+(?:buy\w*|purchas\w*)"
    r"|\b(?:buy\w*|purchas\w*)\s+or\s+(?:rent\w*|leas\w*)",
    re.IGNORECASE,
)

_GOAL_PATTERNS: tuple[tuple[re.Pattern[str], OfferType], ...] = (
    (_UNDECIDED_PATTERN, OfferType.BOTH),
    (re.compile(r"\b(rent|renting|lease|leasing)\b", re.IGNORECASE), OfferType.RENT),
    (re.compile(r"\b(buy|buying|purchase|own|owning)\b", re.IGNORECASE), OfferType.BUY),
    (re.compile(r"\b(either|both|open to)\b", re.IGNORECASE), OfferType.BOTH),
)

#: A goal term the speaker is *ruling out*, not stating. Matching is first-pattern-wins over
#: `_GOAL_PATTERNS` above, so without this "we're planning to buy, not rent" extracts RENT --
#: the rent pattern is simply checked first. Stripping the negated span before matching is
#: what makes the contrast form ("X, not Y" / "rather than Y" / "instead of Y") read as X.
#: Deliberately narrow: only `not`/`rather than`/`instead of` immediately followed by a goal
#: verb, so "not sure whether to rent or buy" (the BOTH pattern's own phrasing) is untouched.
_NEGATED_GOAL_PATTERN = re.compile(
    r"\b(?:not|rather than|instead of|than)\s+"
    r"(?:rent|renting|lease|leasing|buy|buying|purchase|purchasing|own|owning)\b",
    re.IGNORECASE,
)

_CATEGORY_SYNONYMS: dict[str, tuple[VehicleCategory, ...]] = {
    "hatchback": (VehicleCategory.HATCHBACK,),
    "sedan": (VehicleCategory.SEDAN,),
    "suv": (VehicleCategory.SUV,),
    "crossover": (VehicleCategory.CROSSOVER,),
    "coupe": (VehicleCategory.COUPE,),
    "coupé": (VehicleCategory.COUPE,),
    "convertible": (VehicleCategory.CONVERTIBLE,),
    "pickup": (VehicleCategory.PICKUP,),
    "truck": (VehicleCategory.PICKUP,),
    "van": (VehicleCategory.VAN_MPV,),
    "minivan": (VehicleCategory.VAN_MPV,),
    "mpv": (VehicleCategory.VAN_MPV,),
    "wagon": (VehicleCategory.WAGON,),
    "estate": (VehicleCategory.WAGON,),
    "electric": (VehicleCategory.ELECTRIC,),
    "ev": (VehicleCategory.ELECTRIC,),
    "luxury": (VehicleCategory.LUXURY,),
    "sports car": (VehicleCategory.SPORTS,),
    "sports": (VehicleCategory.SPORTS,),
    "family car": (VehicleCategory.SUV, VehicleCategory.VAN_MPV),
    "city car": (VehicleCategory.HATCHBACK,),
}

_BUDGET_PATTERN = re.compile(
    r"(?:€|eur|euros?)\s?([\d][\d,]*(?:\.\d+)?)"
    r"|([\d][\d,]*(?:\.\d+)?)\s?(?:€|eur|euros?)"
    r"|(?:budget(?:\s+is)?|under|up to|max(?:imum)?|around|about)\s*€?\s*([\d][\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)

_DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

_USE_CASE_KEYWORDS = ("commut", "family", "weekend", "road trip", "daily driver", "city driving")

#: "Actually, make it under 20k" (PHASE-3 §3's own example of a mid-RECOMMEND correction)
#: is exactly as authoritative as "my budget is 20k" -- a restatement is a statement.
_LOCKED_MARKERS = (
    "is ",
    "must be",
    "need it by",
    "exactly",
    "no more than",
    "actually",
    "make it",
    "change it to",
    "instead",
)


class DemoSlotExtractor:
    """Regex-and-keyword extraction. Deterministic, no network -- see module docstring."""

    async def extract(self, utterance: str, profile: RequirementProfile) -> tuple[SlotUpdate, ...]:
        updates: list[SlotUpdate] = []
        locked_hint = any(marker in utterance.lower() for marker in _LOCKED_MARKERS)
        confidence = 0.95 if locked_hint else 0.8

        if not profile.goal.is_filled or not profile.goal.locked:
            goal_text = _NEGATED_GOAL_PATTERN.sub(" ", utterance)
            for pattern, offer_type in _GOAL_PATTERNS:
                if pattern.search(goal_text):
                    updates.append(SlotUpdate("goal", offer_type, confidence, locked_hint))
                    break

        categories = _extract_categories(utterance)
        if categories:
            updates.append(SlotUpdate("category", categories, confidence, locked_hint))

        budget = _extract_budget(utterance)
        if budget is not None:
            updates.append(SlotUpdate("budget", budget, confidence, locked_hint))

        target_date = _extract_date(utterance)
        if target_date is not None:
            updates.append(SlotUpdate("target_date", target_date, confidence, locked_hint))

        use_case = _extract_use_case(utterance)
        if use_case is not None:
            updates.append(SlotUpdate("use_case", use_case, 0.6, False))

        return tuple(updates)


def _extract_categories(utterance: str) -> list[VehicleCategory] | None:
    lowered = utterance.lower()
    found: list[VehicleCategory] = []
    for synonym, categories in _CATEGORY_SYNONYMS.items():
        if synonym in lowered:
            for category in categories:
                if category not in found:
                    found.append(category)
    return found or None


def _extract_budget(utterance: str) -> Money | None:
    match = _BUDGET_PATTERN.search(utterance)
    if not match:
        return None
    raw = next(g for g in match.groups() if g is not None)
    return Money.of(raw.replace(",", ""))


def _extract_date(utterance: str) -> date | None:
    match = _DATE_PATTERN.search(utterance)
    if not match:
        return None
    return date.fromisoformat(match.group(1))


def _extract_use_case(utterance: str) -> str | None:
    lowered = utterance.lower()
    for keyword in _USE_CASE_KEYWORDS:
        if keyword in lowered:
            return keyword
    return None


# -- Live extractor -------------------------------------------------------------------------


class ModelSlotExtractor:
    """`claude-haiku-4-5`, one call per turn (PHASE-3 §5). Exercised in live sessions only --
    gate 3.1 runs the ten personas through `DemoSlotExtractor` instead, for the same reason
    D-012 kept gate 2.6 off a live `ClaudeSDKClient`: a check that needs a subprocess and
    credentials is not one CI can run deterministically, and slot extraction's *shape* (one
    call, `Slot` output, folded via `apply_updates`) is what the gate is actually verifying.
    """

    def __init__(self, *, model: str = "claude-haiku-4-5-20251001") -> None:
        self._model = model

    async def extract(self, utterance: str, profile: RequirementProfile) -> tuple[SlotUpdate, ...]:
        import json

        from claude_agent_sdk import ClaudeAgentOptions, query

        from src.agent.prompts import load_prompt

        options = ClaudeAgentOptions(
            model=self._model,
            system_prompt=load_prompt("slot_extraction"),
            max_turns=1,
        )
        payload = {
            "utterance": utterance,
            "profile": profile.model_dump(mode="json"),
        }
        text_out = ""
        async for message in query(prompt=json.dumps(payload), options=options):
            block_text = getattr(message, "result", None)
            if isinstance(block_text, str):
                text_out = block_text

        return _parse_model_output(text_out)


def _parse_model_output(text: str) -> tuple[SlotUpdate, ...]:
    import json

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(parsed, list):
        return ()
    updates: list[SlotUpdate] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        field = entry.get("field")
        if not isinstance(field, str) or field not in RequirementProfile.model_fields:
            continue
        confidence = float(entry.get("confidence", 0.0))
        updates.append(
            SlotUpdate(field, entry.get("value"), confidence, bool(entry.get("locked", False)))
        )
    return tuple(updates)
