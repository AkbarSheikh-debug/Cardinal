"""Builds `booking-mcp` as an `McpSdkServerConfig` (PHASE-2 §3, resources added PHASE-7 §4).

`audience="model"` is what a Claude Agent SDK session gets wired to -- `confirm_booking` and
`submit_booking_draft` are simply absent. `audience="app"` is what our own backend code (the
booking form's submit handler via `src/mcp/apps/proxy.py`, the checkout view's confirm handler
once P8 lands) calls directly. Two different tool sets, same tool definitions, same handlers --
never two implementations of the same tool that could drift apart.

`register_booking_resources` runs regardless of audience: resources aren't gated by the
`audience` mechanism at all (that only ever filters `for_audience`'s tool list), so there's
nothing to choose between here -- every build can answer `resources/read`.
"""

from __future__ import annotations

from claude_agent_sdk import create_sdk_mcp_server
from claude_agent_sdk.types import McpSdkServerConfig

from src.adapters.booking_store import BookingStore
from src.adapters.payments.protocol import PaymentGateway
from src.adapters.store import ListingStore
from src.mcp.audience import Audience, for_audience
from src.mcp.booking.resources import register_booking_resources
from src.mcp.booking.tools import build_tool_specs
from src.mcp.ui.sink import UISink

SERVER_NAME = "booking-mcp"


def build_booking_server(
    *,
    audience: Audience = "model",
    session_id: str = "unbound",
    sink: UISink | None = None,
    store: ListingStore | None = None,
    booking_store: BookingStore | None = None,
    payment_gateway: PaymentGateway | None = None,
) -> McpSdkServerConfig:
    specs = build_tool_specs(
        session_id=session_id,
        sink=sink,
        store=store,
        booking_store=booking_store,
        payment_gateway=payment_gateway,
    )
    config = create_sdk_mcp_server(SERVER_NAME, tools=for_audience(specs, audience))
    register_booking_resources(config)
    return config
