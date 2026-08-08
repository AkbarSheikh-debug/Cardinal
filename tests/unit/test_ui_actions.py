"""Action round-trip parsing (PHASE-6 SS6, gate 6.5). `tests/integration/test_api_ui.py`
exercises the same code through the real FastAPI route; this file pins `parse_action`'s and
`to_user_turn`'s own rules in isolation.
"""

from __future__ import annotations

import pytest

from src.mcp.ui.actions import InvalidActionError, UIAction, parse_action, to_user_turn


def test_parse_action_extracts_full_provenance() -> None:
    action = parse_action(
        {
            "surface": "sess-1:results",
            "component": "card-0",
            "action": "explain",
            "payload": {"sourceId": "AB-1"},
        }
    )
    assert action == UIAction(
        surface="sess-1:results",
        component="card-0",
        action="explain",
        payload={"sourceId": "AB-1"},
    )


def test_parse_action_defaults_payload_to_empty_dict() -> None:
    action = parse_action({"surface": "s", "component": "c", "action": "click"})
    assert action.payload == {}


@pytest.mark.parametrize("missing", ["surface", "component", "action"])
def test_parse_action_rejects_a_missing_required_field(missing: str) -> None:
    body = {"surface": "s", "component": "c", "action": "click"}
    del body[missing]
    with pytest.raises(InvalidActionError):
        parse_action(body)


def test_parse_action_rejects_a_non_object_payload() -> None:
    with pytest.raises(InvalidActionError):
        parse_action({"surface": "s", "component": "c", "action": "click", "payload": "nope"})


def test_to_user_turn_carries_full_provenance() -> None:
    action = UIAction(surface="s", component="c", action="explain", payload={"x": 1})
    turn = to_user_turn(action)
    assert turn["provenance"] == {
        "surface": "s",
        "component": "c",
        "action": "explain",
        "payload": {"x": 1},
    }
