"""The tool protocol layer (PHASE-2). Three MCP servers -- marketplace, ui, booking.

Nothing here decides how the model *should* behave; it decides what the model is even
capable of asking for. These servers must be importable and runnable from a plain script or
from MCP Inspector, not only from behind a running API process, so `src/mcp` carries the
same `fastapi` ban as `src/domain` and `src/agent` (PHASE-0 lint config, not CONSTITUTION
II.1 itself -- but the same reasoning holds).
"""

from __future__ import annotations
