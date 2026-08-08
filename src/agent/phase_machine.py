"""The phase machine (PHASE-3 §3). Code-owned transitions and turn budgets.

The model never decides it is "done interviewing" -- these functions do, evaluated against
the typed `RequirementProfile`. Pure and I/O-free, so the whole state machine is testable
with no event loop, no SDK and no database -- the same reasoning CONSTITUTION II.1 applies
to `src/domain`, applied here to the one corner of `src/agent` that has no excuse to need
anything more.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domain.profile import RequirementProfile


class Phase(StrEnum):
    INTERVIEW = "interview"
    RESEARCH = "research"
    RECOMMEND = "recommend"
    TRANSACT = "transact"


#: PHASE-3 §3's table. Applied as a hard cap in every phase, not only the two rows that spell
#: out what happens when it's hit -- a budget nobody enforces isn't a budget.
TURN_BUDGETS: dict[Phase, int] = {
    Phase.INTERVIEW: 12,
    Phase.RESEARCH: 6,
    Phase.RECOMMEND: 10,
    Phase.TRANSACT: 8,
}

#: TRANSACT's exit predicate is "booking reaches a terminal state" -- P8 owns what a real
#: terminal state is. As far as P3 can drive a booking (no `confirm_booking`, no payment),
#: a submitted draft or an opened checkout is as terminal as this phase gets.
TRANSACT_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"draft_submitted", "checkout_opened", "abandoned"}
)

_NEXT_PHASE: dict[Phase, Phase | None] = {
    Phase.INTERVIEW: Phase.RESEARCH,
    Phase.RESEARCH: Phase.RECOMMEND,
    Phase.RECOMMEND: Phase.TRANSACT,
    Phase.TRANSACT: None,
}


class SessionState(BaseModel):
    """Everything the phase machine needs to decide what happens next. Durable (P3 §8
    gate 3.2): this is exactly what a `SessionStore` persists and restores by `session_id`.
    """

    model_config = ConfigDict(frozen=True)

    session_id: str
    phase: Phase = Phase.INTERVIEW
    turn_in_phase: int = Field(default=0, ge=0)
    total_turns: int = Field(default=0, ge=0)
    profile: RequirementProfile = Field(default_factory=RequirementProfile)
    candidate_ids: tuple[str, ...] = ()
    ranked: bool = False
    selected_candidate: str | None = None
    disengaged: bool = False
    booking_status: str | None = None
    infeasible: bool = Field(
        default=False,
        description="RESEARCH's budget ran out with zero candidates. [SCALE] P5 branches "
        "this into a counterfactual; P3 just carries the flag forward honestly.",
    )

    @property
    def budget(self) -> int:
        return TURN_BUDGETS[self.phase]

    @property
    def budget_exhausted(self) -> bool:
        return self.turn_in_phase >= self.budget


def new_session(session_id: str) -> SessionState:
    return SessionState(session_id=session_id)


def begin_turn(state: SessionState) -> SessionState:
    """Call once per user turn, before any tool call or phase logic runs."""
    return state.model_copy(
        update={
            "turn_in_phase": state.turn_in_phase + 1,
            "total_turns": state.total_turns + 1,
        }
    )


def _exit_predicate_met(state: SessionState) -> bool:
    if state.phase is Phase.INTERVIEW:
        return state.profile.is_complete
    if state.phase is Phase.RESEARCH:
        return len(state.candidate_ids) >= 1
    if state.phase is Phase.RECOMMEND:
        return state.selected_candidate is not None or state.disengaged
    if state.phase is Phase.TRANSACT:
        return state.booking_status in TRANSACT_TERMINAL_STATUSES
    raise AssertionError(f"unreachable: unhandled phase {state.phase!r}")


def advance(state: SessionState) -> SessionState:
    """Move to the next phase if this phase's exit predicate holds, or the turn budget
    forces it. A no-op on most turns -- phase changes are the exception, not the rule.
    """
    if state.phase is Phase.TRANSACT:
        return state  # terminal within P3's scope; nothing after it until P8
    if _exit_predicate_met(state):
        return _enter_next_phase(state)
    if state.budget_exhausted:
        return _enter_next_phase(state, forced=True)
    return state


def _enter_next_phase(state: SessionState, *, forced: bool = False) -> SessionState:
    next_phase = _NEXT_PHASE[state.phase]
    assert next_phase is not None, f"{state.phase} has no next phase"
    updates: dict[str, Any] = {"phase": next_phase, "turn_in_phase": 0}
    if forced and next_phase is Phase.RECOMMEND and not state.candidate_ids:
        updates["infeasible"] = True
    return state.model_copy(update=updates)


def apply_profile_update(state: SessionState, profile: RequirementProfile) -> SessionState:
    """A new or changed answer arrives. Outside RECOMMEND this is just bookkeeping; inside
    it, a REQUIRED-slot change invalidates whatever was already ranked and shown.

    PHASE-3 §3: "Actually, make it under 20k" mid-RECOMMEND returns to RESEARCH and
    re-ranks -- handled explicitly here, not left for the model to notice on its own.
    """
    if state.phase is Phase.RECOMMEND and _required_slots_changed(state.profile, profile):
        return state.model_copy(
            update={
                "profile": profile,
                "phase": Phase.RESEARCH,
                "turn_in_phase": 0,
                "candidate_ids": (),
                "ranked": False,
                "selected_candidate": None,
            }
        )
    return state.model_copy(update={"profile": profile})


def _required_slots_changed(before: RequirementProfile, after: RequirementProfile) -> bool:
    return any(
        getattr(before, name).value != getattr(after, name).value
        for name in RequirementProfile.REQUIRED
    )
