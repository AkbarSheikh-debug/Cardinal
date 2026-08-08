"""Host-side MCP Apps plumbing (PHASE-7): resource-agnostic pieces every `ui://`-serving
server can share -- CSP/`_meta.ui` shape, the view-RPC proxy, the audit log. `booking-mcp` is
the only caller today; P8's checkout app is meant to be the second one, per PROGRESS.md's own
note when P6 landed.
"""

from __future__ import annotations
