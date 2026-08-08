"""Turn processing for the INTERVIEW phase and beyond.

One implementation both `demo.py` and `orchestrator.py` call through, so "how a user
utterance becomes a profile update, and whether that moves the phase machine" exists exactly
once -- the same reasoning PHASE-2's dual-transport `marketplace-mcp` uses (one `Server`
instance backs both builds) applied to turn processing instead of tool serving.
"""

from __future__ import annotations

from src.agent.extraction import SlotExtractor, apply_updates
from src.agent.phase_machine import SessionState, advance, apply_profile_update, begin_turn


async def process_turn(
    state: SessionState, utterance: str, extractor: SlotExtractor
) -> SessionState:
    """One user utterance -> extracted slot updates -> possibly a phase change.

    Safe to call in any phase, not only INTERVIEW: a stated constraint mid-RECOMMEND is what
    triggers the backward transition in `apply_profile_update` (PHASE-3 §3, gate 3.5), and
    outside RECOMMEND an update is just bookkeeping that doesn't change the phase.
    """
    turned = begin_turn(state)
    updates = await extractor.extract(utterance, turned.profile)
    new_profile = apply_updates(turned.profile, updates, turn=turned.total_turns)
    updated = apply_profile_update(turned, new_profile)
    return advance(updated)
