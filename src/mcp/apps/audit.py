"""View-initiated RPC audit log (PHASE-7 SS5.5, CONSTITUTION II.5, `plans/GUARDRAILS.md`'s
"View->server traffic is proxied" row).

Every request the host proxies on a view's behalf is recorded here -- not the tool/resource
handler's own business logic, just the fact that a request happened, what it was, and what the
host decided to do with it. This is what makes "the view never talks to the server directly"
more than a claim: a compromised or merely buggy App can only ever produce entries in this log,
never an unaudited network call, because `src/mcp/apps/proxy.py` is the only path from a view to
`booking-mcp` and it writes one of these on every call, allowed or blocked.

In-memory, per-process -- the same convention `src/agent/guardrails.py`'s `AuditLog` uses for
gate 3.6's PreToolUse trail, applied here to view-initiated RPC instead of model-initiated tool
calls. `[SCALE]` is durable storage; the shape doesn't change when that lands, only where it's
kept.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Literal

Decision = Literal["allowed", "blocked"]


@dataclass(frozen=True)
class AuditEntry:
    timestamp: float
    session_id: str
    resource_uri: str
    method: str
    params_hash: str
    decision: Decision
    result_status: str


def hash_params(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class AppAuditLog:
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(
        self,
        *,
        session_id: str,
        resource_uri: str,
        method: str,
        params: dict[str, Any],
        decision: Decision,
        result_status: str,
    ) -> AuditEntry:
        entry = AuditEntry(
            timestamp=time.time(),
            session_id=session_id,
            resource_uri=resource_uri,
            method=method,
            params_hash=hash_params(params),
            decision=decision,
            result_status=result_status,
        )
        self._entries.append(entry)
        return entry

    def for_session(self, session_id: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.session_id == session_id]

    def all(self) -> list[AuditEntry]:
        return list(self._entries)
