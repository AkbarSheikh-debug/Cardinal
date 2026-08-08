"""The payment gateway protocol (PHASE-8 §5). Three methods, chosen so that swapping in a
real provider later is one new file implementing them -- nothing above this seam changes,
the same promise `src/adapters/protocol.py`'s `MarketplaceAdapter` makes for marketplaces.

`[SCALE]` per PHASE-8 §2: a real provider behind this same protocol, feature-flagged. Nothing
about that lands here -- there is deliberately no second implementation of this protocol in
this repository, real or otherwise (CONSTITUTION I.1, gate 8.7).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.payments import AuthResult, CaptureResult, PaymentIntent, VoidResult


@runtime_checkable
class PaymentGateway(Protocol):
    async def authorise(self, intent: PaymentIntent, idem: str) -> AuthResult: ...

    async def capture(self, auth_id: str, idem: str) -> CaptureResult: ...

    async def void(self, auth_id: str, idem: str) -> VoidResult: ...
