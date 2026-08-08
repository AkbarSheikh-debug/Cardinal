"""`booking-mcp` -- form-fill and checkout tools (PHASE-2 §4).

`confirm_booking` (and `submit_booking_draft`, which is also view-initiated only) carry
`audience=("app",)`. That tuple is CONSTITUTION I.2's enforcement mechanism: a model-facing
server built from this module's `build_tool_specs()` never has those two tools registered on
it in the first place, so there is no permission check to bypass and no prompt to talk the
model past -- the tool is not there.
"""

from __future__ import annotations
