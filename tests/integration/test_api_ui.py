"""PHASE-6 SS6's transport, exercised through the real FastAPI app (`src/api/main.py`):
the action round-trip (gate 6.5) via `TestClient`, and the SSE frame relay directly against
`session_events`'s own generator (a raw `GET` against an infinite stream has no natural end,
so that half is driven with a bounded `asyncio.wait_for` instead of going through HTTP).
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from src.agent.orchestrator import CardinalOrchestrator
from src.api.main import _sse_frame, app


def test_action_round_trip_reaches_the_agent_session_with_full_provenance() -> None:
    """Gate 6.5: a simulated click reaches the agent session with full provenance."""
    with TestClient(app) as client:
        session_id = "gate65-session"
        response = client.post(
            f"/sessions/{session_id}/actions",
            json={
                "surface": f"{session_id}:results",
                "component": "card-0",
                "action": "explain",
                "payload": {"sourceId": "AB-1"},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["provenance"] == {
            "surface": f"{session_id}:results",
            "component": "card-0",
            "action": "explain",
            "payload": {"sourceId": "AB-1"},
        }

        orchestrator: CardinalOrchestrator = app.state.orchestrator
        recorded = orchestrator.actions_for(session_id)
        assert len(recorded) == 1
        assert recorded[0] == body


def test_action_round_trip_rejects_a_malformed_payload() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/sessions/gate65-bad/actions", json={"surface": "s", "action": "click"}
        )
        assert response.status_code == 422


def test_sse_frame_format_is_one_data_line_per_message() -> None:
    message = {"version": "v0.9", "createSurface": {"surfaceId": "s:1", "catalogId": "c"}}
    frame = _sse_frame(message)
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    assert '"surfaceId": "s:1"' in frame


async def test_ui_sink_stream_relays_pushed_messages_in_order() -> None:
    orchestrator = CardinalOrchestrator()
    sink = orchestrator.ui_sink("sess-x")
    await sink.push([{"a": 1}, {"a": 2}])

    stream = sink.stream()
    first = await asyncio.wait_for(stream.__anext__(), timeout=1.0)
    second = await asyncio.wait_for(stream.__anext__(), timeout=1.0)
    assert [first, second] == [{"a": 1}, {"a": 2}]


def test_ui_sink_is_stable_across_calls_for_the_same_session() -> None:
    orchestrator = CardinalOrchestrator()
    assert orchestrator.ui_sink("sess-y") is orchestrator.ui_sink("sess-y")
