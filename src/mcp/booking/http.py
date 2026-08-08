"""Standalone HTTP transport for `booking-mcp` (PHASE-2 §3).

    python -m src.mcp.booking.http

`booking-mcp` is HTTP, not stdio or in-process, because it has to serve `ui://` resources the
browser fetches through the host proxy (P7) and because a compromised or slow marketplace
server should not be able to take checkout down with it (PHASE-2 §3). No `fastapi` import:
`StreamableHTTPSessionManager` is Starlette-based, which is what makes an HTTP-transport MCP
server possible in a module that carries the same `fastapi` ban as `src/domain`.

The `audience="model"` server is what P3's agent integration will point at; there is no
`audience="app"` HTTP route here, because app-only tools are called in-process by our own
backend code, never over this transport.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from src.mcp.booking.server import build_booking_server

DEFAULT_PORT = 8100

#: Overridable so this module can bind `0.0.0.0` inside its own container (PHASE-11 §3: a
#: separate compose service, its own hostname) instead of the loopback-only default a locally
#: spawned subprocess (`src/api/main.py`'s `_ensure_booking_mcp_http`) uses. Unset in both
#: places -- local dev and every gate through P10 -- so this changes nothing for either.
ENV_HOST = "BOOKING_MCP_HTTP_HOST"
ENV_PORT = "BOOKING_MCP_HTTP_PORT"


def _host() -> str:
    return os.environ.get(ENV_HOST, "127.0.0.1")


def _port() -> int:
    return int(os.environ.get(ENV_PORT, str(DEFAULT_PORT)))


def build_app() -> Starlette:
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    config = build_booking_server(audience="model")
    session_manager = StreamableHTTPSessionManager(app=config["instance"])

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    return Starlette(routes=[Mount("/mcp", app=handle_mcp)], lifespan=lifespan)


def main() -> None:
    uvicorn.run(build_app(), host=_host(), port=_port())


if __name__ == "__main__":
    main()
