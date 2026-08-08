"""`marketplace-mcp` -- search, get, availability, quote, compare (PHASE-2 §4).

The only server with real handler bodies in P2: everything it needs already exists in P1's
adapters and `ListingStore`. It searches across every registered source at once -- the model
never learns which marketplace a result came from, per CONSTITUTION II.6.
"""

from __future__ import annotations
