"""`ui://booking/form` and `ui://checkout/payment` -- the two resources `booking-mcp` serves
(PHASE-7 SS4/SS6, PHASE-8 §2 brief requirement R4).

Registered directly on the low-level `Server` `create_sdk_mcp_server` hands back
(`config["instance"]`): that object already supports `@server.list_resources()` /
`@server.read_resource()` the same way it supports `@server.list_tools()` /
`@server.call_tool()` internally (see `src/mcp/audience.py`'s docstring on why reading the real
handler beats the SDK's own bookkeeping). `create_sdk_mcp_server` itself only wires tools, so
this is additive registration on the same server instance, not a workaround.

`ui://checkout/payment` is a second resource on the *same* server, not a second host
implementation -- PROGRESS.md's own note when P7 landed: "`src/mcp/apps/` was built
resource-agnostic specifically so P8 is a second resource + a second `RESOURCE_ROUTES` entry."
"""

from __future__ import annotations

from pathlib import Path

from claude_agent_sdk.types import McpSdkServerConfig
from mcp.server.lowlevel.helper_types import ReadResourceContents

from mcp import types as mcp_types
from src.mcp.apps.meta import resource_ui_meta

BOOKING_FORM_URI = "ui://booking/form"
CHECKOUT_URI = "ui://checkout/payment"

#: Which `tools/call` names a view may invoke against which resource (PHASE-7 SS5.3: "the view
#: never talks to the server directly" cuts both ways -- it also never gets a blank cheque once
#: it *is* talking through the host). `open_checkout`/`confirm_booking` belong to different
#: resources than `submit_booking_draft`; a view for the booking form has no business calling
#: `confirm_booking` even though the underlying server registers it.
ALLOWED_VIEW_TOOLS: dict[str, frozenset[str]] = {
    BOOKING_FORM_URI: frozenset({"submit_booking_draft"}),
    CHECKOUT_URI: frozenset({"mint_gesture_token", "confirm_booking"}),
}

_STATIC_DIR = Path(__file__).resolve().parent / "static"

_RESOURCES: dict[str, dict[str, str]] = {
    BOOKING_FORM_URI: {
        "file": "booking_form.html",
        "name": "Booking form",
        "description": "Buyer/renter details, dates, collection location, add-ons.",
    },
    CHECKOUT_URI: {
        "file": "checkout.html",
        "name": "Checkout",
        "description": "Priced total, optional financing, mock card payment. "
        "MOCK -- NO REAL PAYMENT.",
    },
}


def _resource_html(uri: str) -> str:
    return (_STATIC_DIR / _RESOURCES[uri]["file"]).read_text(encoding="utf-8")


def register_booking_resources(config: McpSdkServerConfig) -> None:
    server = config["instance"]

    @server.list_resources()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_resources() -> list[mcp_types.Resource]:
        return [
            mcp_types.Resource(
                uri=mcp_types.AnyUrl(uri),
                name=meta["name"],
                description=meta["description"],
                mimeType="text/html;profile=mcp-app",
                # `Resource.meta` is `Field(alias="_meta")` -- pydantic validates constructor
                # kwargs by alias, not by attribute name, so `meta=` here would silently land
                # as an unrelated `extra="allow"` field instead of the real one.
                **{"_meta": resource_ui_meta(connect_domains=(), prefers_border=True)},
            )
            for uri, meta in _RESOURCES.items()
        ]

    @server.read_resource()  # type: ignore[no-untyped-call,untyped-decorator]
    async def read_resource(uri: mcp_types.AnyUrl) -> list[ReadResourceContents]:
        if str(uri) not in _RESOURCES:
            raise ValueError(f"unknown resource: {uri}")
        return [
            ReadResourceContents(
                content=_resource_html(str(uri)),
                mime_type="text/html;profile=mcp-app",
                meta=resource_ui_meta(connect_domains=(), prefers_border=True),
            )
        ]
