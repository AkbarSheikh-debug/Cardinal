"""Gesture tokens (PHASE-8 §4, CONSTITUTION I.2's third layer of defence).

Tool visibility (gate 8.2) and `can_use_tool` (layer 2) are what stop the *model* from ever
reaching `confirm_booking`. Neither says anything about a browser calling it directly, and
neither would survive a future refactor that accidentally widened `confirm_booking`'s
audience. This is the layer that does: `confirm_booking` additionally requires a token this
module minted in response to a real, trusted `click` -- `mint_gesture_token` is itself
`APP_ONLY` and is only ever invoked from the checkout App's own click handler, after it has
checked `event.isTrusted` (`src/mcp/booking/static/checkout.html`). A token is single-use and
expires 30 seconds after minting, so even a captured or replayed token is a narrow, one-shot
window, not a standing bypass.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

#: PHASE-8 §4: "valid for 30 seconds."
GESTURE_TOKEN_TTL_SECONDS = 30


@dataclass
class _Token:
    booking_draft_id: str
    minted_at: float


class GestureTokenStore:
    """In-memory, per-process -- the same posture P7's `_booking_drafts` and
    `src/mcp/apps/audit.py`'s `AppAuditLog` use for their own first working stores. A token
    is a 30-second-lived, single-use credential; there is nothing here worth a database row.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, _Token] = {}

    def mint(self, booking_draft_id: str) -> str:
        token = secrets.token_urlsafe(24)
        self._tokens[token] = _Token(booking_draft_id=booking_draft_id, minted_at=time.monotonic())
        return token

    def consume(self, token: str, *, booking_draft_id: str) -> tuple[bool, str]:
        """Single-use: removed on every call regardless of outcome, so a stolen-and-replayed
        token cannot be tried twice even within its 30-second window. Returns `(ok, reason)`
        rather than raising -- the caller turns a rejection into a normal (non-exception) tool
        result, gate 8.4's "rejected", not a 500.
        """
        record = self._tokens.pop(token, None)
        if record is None:
            return False, "gesture token is missing, unknown, or already used"
        if record.booking_draft_id != booking_draft_id:
            return False, "gesture token was minted for a different booking draft"
        age_seconds = time.monotonic() - record.minted_at
        if age_seconds > GESTURE_TOKEN_TTL_SECONDS:
            return False, (
                f"gesture token expired {age_seconds - GESTURE_TOKEN_TTL_SECONDS:.1f}s ago "
                f"(valid for {GESTURE_TOKEN_TTL_SECONDS}s)"
            )
        return True, "ok"
