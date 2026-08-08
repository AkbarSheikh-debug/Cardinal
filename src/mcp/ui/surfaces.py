"""Surface identity (PHASE-6 SS6, gate 6.6): `createSurface` once per logical view, then
`updateComponents` to mutate it. Re-creating a surface every turn destroys scroll position,
loses focus, and flickers -- "which reads as 'prototype' instantly" (PHASE-6 SS6).

A surface's id is derived, not generated: `f"{session_id}:{kind}"` is stable across calls
with no registry lookup needed to compute it, and `SurfaceRegistry` only has to remember
*whether* it has been created yet, not invent an id for it.
"""

from __future__ import annotations

from enum import StrEnum


class SurfaceKind(StrEnum):
    PROGRESS = "progress"
    RESULTS = "results"
    DETAIL = "detail"
    TCO = "tco"
    SCORE_BREAKDOWN = "score_breakdown"
    COMPOSE = "compose"


def surface_id(session_id: str, kind: SurfaceKind) -> str:
    return f"{session_id}:{kind.value}"


class SurfaceRegistry:
    """Tracks which surfaces a session has already created. One instance per running process
    is enough for the in-process `ui-mcp` server (PHASE-2 SS3); a live multi-process deployment
    would back this with the same store `SessionStateStore` already durable-writes to, which is
    a storage swap, not a redesign, since the registry's whole state is one set of strings.
    """

    def __init__(self) -> None:
        self._created: set[str] = set()

    def ensure_created(self, session_id: str, kind: SurfaceKind) -> tuple[str, bool]:
        """Returns `(surface_id, needs_create_message)`. The second call for the same
        `(session_id, kind)` pair always returns `False` -- gate 6.6's whole assertion.
        """
        sid = surface_id(session_id, kind)
        if sid in self._created:
            return sid, False
        self._created.add(sid)
        return sid, True

    def forget(self, session_id: str, kind: SurfaceKind) -> None:
        self._created.discard(surface_id(session_id, kind))

    def forget_session(self, session_id: str) -> None:
        prefix = f"{session_id}:"
        self._created = {sid for sid in self._created if not sid.startswith(prefix)}
