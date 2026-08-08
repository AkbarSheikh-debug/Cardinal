"""Orchestration (PHASE-3). Phase machine, subagent roster, guardrails, session durability,
demo mode. Imports `domain` and `adapters`; never `fastapi` (CONSTITUTION II.1) -- this
package must run from a plain Python script, same as `src/domain`.
"""

from __future__ import annotations
