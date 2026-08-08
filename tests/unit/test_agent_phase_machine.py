"""The phase machine (PHASE-3 §3): turn budgets, exit predicates, backward transitions."""

from __future__ import annotations

from datetime import date

from src.agent.phase_machine import (
    TRANSACT_TERMINAL_STATUSES,
    TURN_BUDGETS,
    Phase,
    advance,
    apply_profile_update,
    begin_turn,
    new_session,
)
from src.domain.enums import OfferType, VehicleCategory
from src.domain.money import Money
from src.domain.profile import RequirementProfile


def _complete_profile() -> RequirementProfile:
    profile = RequirementProfile()
    profile.goal = profile.goal.fill(OfferType.BUY, confidence=0.9, turn=1, locked=True)
    profile.category = profile.category.fill(
        [VehicleCategory.SUV], confidence=0.9, turn=1, locked=True
    )
    profile.budget = profile.budget.fill(Money.of("20000"), confidence=0.9, turn=1, locked=True)
    profile.target_date = profile.target_date.fill(
        date(2026, 9, 1), confidence=0.9, turn=1, locked=True
    )
    return profile


def test_new_session_starts_in_interview_with_zero_turns() -> None:
    state = new_session("s1")
    assert state.phase is Phase.INTERVIEW
    assert state.turn_in_phase == 0
    assert state.total_turns == 0


def test_begin_turn_increments_both_counters() -> None:
    state = new_session("s1")
    state = begin_turn(state)
    state = begin_turn(state)
    assert state.turn_in_phase == 2
    assert state.total_turns == 2


def test_advance_is_a_noop_when_exit_predicate_not_met_and_budget_not_exhausted() -> None:
    state = new_session("s1")
    state = begin_turn(state)
    assert advance(state) == state


def test_interview_advances_to_research_when_profile_complete() -> None:
    state = new_session("s1")
    state = state.model_copy(update={"profile": _complete_profile()})
    state = advance(state)
    assert state.phase is Phase.RESEARCH
    assert state.turn_in_phase == 0


def test_interview_forced_exit_at_budget_even_if_incomplete() -> None:
    state = new_session("s1")
    for _ in range(TURN_BUDGETS[Phase.INTERVIEW]):
        state = begin_turn(state)
    assert state.turn_in_phase == TURN_BUDGETS[Phase.INTERVIEW]
    assert not state.profile.is_complete
    state = advance(state)
    assert state.phase is Phase.RESEARCH


def test_interview_does_not_force_exit_one_turn_before_budget() -> None:
    state = new_session("s1")
    for _ in range(TURN_BUDGETS[Phase.INTERVIEW] - 1):
        state = begin_turn(state)
    state = advance(state)
    assert state.phase is Phase.INTERVIEW


def test_research_advances_to_recommend_on_first_candidate() -> None:
    state = new_session("s1")
    state = state.model_copy(update={"phase": Phase.RESEARCH, "candidate_ids": ("a:1",)})
    state = advance(state)
    assert state.phase is Phase.RECOMMEND


def test_research_forced_exit_marks_infeasible_when_no_candidates_survive_budget() -> None:
    state = new_session("s1")
    state = state.model_copy(update={"phase": Phase.RESEARCH})
    for _ in range(TURN_BUDGETS[Phase.RESEARCH]):
        state = begin_turn(state)
    state = advance(state)
    assert state.phase is Phase.RECOMMEND
    assert state.infeasible is True


def test_recommend_advances_to_transact_on_selection() -> None:
    state = new_session("s1")
    state = state.model_copy(update={"phase": Phase.RECOMMEND, "selected_candidate": "a:1"})
    state = advance(state)
    assert state.phase is Phase.TRANSACT


def test_recommend_advances_to_transact_on_disengage() -> None:
    state = new_session("s1")
    state = state.model_copy(update={"phase": Phase.RECOMMEND, "disengaged": True})
    state = advance(state)
    assert state.phase is Phase.TRANSACT


def test_transact_is_terminal_within_p3_scope() -> None:
    state = new_session("s1")
    state = state.model_copy(update={"phase": Phase.TRANSACT})
    assert advance(state) == state
    state = state.model_copy(update={"booking_status": "draft_submitted"})
    assert state.booking_status in TRANSACT_TERMINAL_STATUSES
    # Still terminal -- P3 has nothing after TRANSACT (P8 owns what comes next).
    assert advance(state) == state


def test_backward_transition_from_recommend_on_required_slot_change() -> None:
    state = new_session("s1")
    state = state.model_copy(
        update={
            "phase": Phase.RECOMMEND,
            "profile": _complete_profile(),
            "candidate_ids": ("a:1", "a:2"),
            "ranked": True,
        }
    )
    changed = _complete_profile()
    changed.budget = changed.budget.fill(Money.of("15000"), confidence=0.95, turn=5, locked=True)
    state = apply_profile_update(state, changed)
    assert state.phase is Phase.RESEARCH
    assert state.turn_in_phase == 0
    assert state.candidate_ids == ()
    assert state.ranked is False
    assert state.selected_candidate is None


def test_profile_update_outside_recommend_does_not_change_phase() -> None:
    state = new_session("s1")
    changed = _complete_profile()
    state = apply_profile_update(state, changed)
    assert state.phase is Phase.INTERVIEW
    assert state.profile == changed


def test_profile_update_in_recommend_with_no_required_change_stays_in_recommend() -> None:
    profile = _complete_profile()
    state = new_session("s1")
    state = state.model_copy(update={"phase": Phase.RECOMMEND, "profile": profile})
    # A use_case update is not a REQUIRED slot -- should not invalidate the ranking.
    updated_profile = profile.model_copy()
    updated_profile.use_case = updated_profile.use_case.fill("commuting", confidence=0.6, turn=9)
    state = apply_profile_update(state, updated_profile)
    assert state.phase is Phase.RECOMMEND
