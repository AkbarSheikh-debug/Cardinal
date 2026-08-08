"""The view-RPC proxy (PHASE-7 SS5.3): the *only* path from a browser to `booking-mcp`.

`tools/call` and `resources/read` from a view are proxied through the host to the real MCP
server -- never called by the view directly -- which is what makes the audit log complete and
the CSP meaningful (PHASE-7 SS5.3's own words). `src/api` calls `call_view_rpc` from one HTTP
route (`POST /mcp-apps/{session_id}/rpc`), the only thing a browser (outer iframe, host origin)
ever talks to. From there the two methods a view may invoke take genuinely different paths,
matching what each part of `booking-mcp` was actually built for:

- `resources/read` goes over a real `mcp.client.streamable_http` session to `booking-mcp`'s
  standalone HTTP transport (`src/mcp/booking/http.py`, loopback-only, never reachable from the
  browser) -- that module exists specifically "because it has to serve `ui://` resources the
  browser fetches through the host proxy" (its own docstring).
- `tools/call` is dispatched in-process, straight into an `audience="app"` server's own
  `call_tool` handler -- the same docstring's other half: "app-only tools are called in-process
  by our own backend code, never over this transport." `submit_booking_draft` mutating
  in-memory state through a serialised MCP-over-HTTP round trip would be a second, redundant
  hop for no isolation benefit `resources/read` doesn't already provide.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from claude_agent_sdk.types import McpSdkServerConfig
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from mcp import types as mcp_types
from src.mcp.apps.audit import AppAuditLog

_RPC_TIMEOUT = timedelta(seconds=10)


class AppRpcError(Exception):
    """A view asked for something it isn't permitted to do. Always audited as `blocked` before
    this is raised -- the caller's job is turning it into an HTTP error, not re-auditing it.
    """


def _is_permitted(*, method: str, params: dict[str, Any], allowed_tools: frozenset[str]) -> bool:
    if method == "resources/read":
        return True
    if method == "tools/call":
        name = params.get("name")
        return isinstance(name, str) and name in allowed_tools
    return False


async def _read_resource_via_http(*, server_url: str, uri: str) -> dict[str, Any]:
    async with streamablehttp_client(server_url) as (read_stream, write_stream, _get_session_id):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.read_resource(mcp_types.AnyUrl(uri))
            return result.model_dump(mode="json", by_alias=True)


async def _call_tool_in_process(
    *, config: McpSdkServerConfig, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Reaches the *real* registered handler the same way `src/mcp/audience.py`'s
    `resolved_tools` does for `tools/list` -- `server.request_handlers`, not a shortcut that
    calls the Python function directly and skips whatever `create_sdk_mcp_server` wires around
    it (input validation, content-block shaping).
    """
    server = config["instance"]
    handler = server.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments)
    )
    server_result = await handler(request)
    return server_result.root.model_dump(mode="json", by_alias=True)


async def call_view_rpc(
    *,
    session_id: str,
    resource_uri: str,
    method: str,
    params: dict[str, Any],
    resource_server_url: str,
    app_tool_config: McpSdkServerConfig,
    allowed_tools: frozenset[str],
    audit: AppAuditLog,
) -> dict[str, Any]:
    """Proxies one view-initiated RPC. Raises `AppRpcError` for anything not on the allowlist
    (audited as `blocked`); re-raises any transport/server failure after auditing it as an
    error result -- callers see a real failure, never a silently swallowed one.
    """
    if method not in {"resources/read", "tools/call"} or not _is_permitted(
        method=method, params=params, allowed_tools=allowed_tools
    ):
        audit.record(
            session_id=session_id,
            resource_uri=resource_uri,
            method=method,
            params=params,
            decision="blocked",
            result_status="rejected: not permitted for this view",
        )
        raise AppRpcError(f"{method} is not permitted for {resource_uri}")

    try:
        if method == "resources/read":
            result = await _read_resource_via_http(
                server_url=resource_server_url, uri=params["uri"]
            )
        else:
            result = await _call_tool_in_process(
                config=app_tool_config, name=params["name"], arguments=params.get("arguments") or {}
            )
    except Exception as exc:
        audit.record(
            session_id=session_id,
            resource_uri=resource_uri,
            method=method,
            params=params,
            decision="allowed",
            result_status=f"error: {exc}",
        )
        raise

    audit.record(
        session_id=session_id,
        resource_uri=resource_uri,
        method=method,
        params=params,
        decision="allowed",
        result_status="ok",
    )
    return result
