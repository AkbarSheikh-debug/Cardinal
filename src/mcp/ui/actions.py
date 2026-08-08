"""Action round-trip (PHASE-6 SS6, gate 6.5): the renderer's `actionHandler` posts here, and
this module turns that into a user turn the agent session can see, carrying full provenance
(`{surface, component, action, payload}`) rather than the agent inferring a click happened
from prose.

Pure and I/O-free on purpose -- `src/api`'s `POST /sessions/{id}/actions` route is the only
caller, and it does the actual queuing/injection; this module only knows how to parse and
shape one action, the same domain/transport split every other layer in this repo keeps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class InvalidActionError(ValueError):
    pass


@dataclass(frozen=True)
class UIAction:
    surface: str
    component: str
    action: str
    payload: dict[str, Any]


_REQUIRED_KEYS = ("surface", "component", "action")


def parse_action(body: dict[str, Any]) -> UIAction:
    missing = [k for k in _REQUIRED_KEYS if not isinstance(body.get(k), str) or not body[k]]
    if missing:
        raise InvalidActionError(f"action payload missing required field(s): {missing}")
    payload = body.get("payload", {})
    if not isinstance(payload, dict):
        raise InvalidActionError("'payload' must be an object")
    return UIAction(
        surface=body["surface"],
        component=body["component"],
        action=body["action"],
        payload=payload,
    )


def to_user_turn(action: UIAction) -> dict[str, Any]:
    """The shape injected into the agent session in place of a typed utterance -- structured
    provenance the model can reason over directly, instead of narrating a click as prose the
    orchestrator would have to parse back out again.
    """
    return {
        "role": "user",
        "kind": "ui_action",
        "provenance": {
            "surface": action.surface,
            "component": action.component,
            "action": action.action,
            "payload": action.payload,
        },
    }
