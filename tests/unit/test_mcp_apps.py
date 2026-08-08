"""`src/mcp/apps/` -- the host-side plumbing PHASE-7's gate exercises end-to-end through a real
browser. These tests pin the pure/unit-level pieces (audit log bookkeeping, CSP defaults, the
view-RPC permission check) at the unit level, the same division of labour PHASE-2's tests use
for `src/mcp/audience.py` alongside gate 2.6's own end-to-end proof.
"""

from __future__ import annotations

import pytest

from src.mcp.apps.audit import AppAuditLog, hash_params
from src.mcp.apps.meta import DEFAULT_CSP, csp_header_value, effective_csp, resource_ui_meta
from src.mcp.apps.proxy import AppRpcError, call_view_rpc


def test_resource_ui_meta_shape() -> None:
    meta = resource_ui_meta(connect_domains=("https://pay.example",), prefers_border=True)
    csp = {"connectDomains": ["https://pay.example"]}
    assert meta == {"ui": {"csp": csp, "prefersBorder": True}}


def test_effective_csp_defaults_when_no_domains_declared() -> None:
    assert effective_csp(()) == DEFAULT_CSP
    assert effective_csp(())["connect-src"] == "'none'"


def test_effective_csp_widens_connect_src_only() -> None:
    csp = effective_csp(("https://pay.example", "https://cdn.example"))
    assert csp["connect-src"] == "'self' https://pay.example https://cdn.example"
    # every other directive is untouched by widening connect-src
    for directive in ("default-src", "script-src", "style-src", "img-src", "media-src"):
        assert csp[directive] == DEFAULT_CSP[directive]


def test_csp_header_value_joins_directives() -> None:
    header = csp_header_value({"default-src": "'none'", "script-src": "'self'"})
    assert header == "default-src 'none'; script-src 'self'"


def test_audit_log_records_and_filters_by_session() -> None:
    audit = AppAuditLog()
    audit.record(
        session_id="s1",
        resource_uri="ui://booking/form",
        method="resources/read",
        params={"uri": "ui://booking/form"},
        decision="allowed",
        result_status="ok",
    )
    audit.record(
        session_id="s2",
        resource_uri="ui://booking/form",
        method="tools/call",
        params={"name": "confirm_booking"},
        decision="blocked",
        result_status="rejected: not permitted for this view",
    )
    assert len(audit.all()) == 2
    s1_entries = audit.for_session("s1")
    assert len(s1_entries) == 1
    assert s1_entries[0].method == "resources/read"
    assert s1_entries[0].decision == "allowed"


def test_hash_params_is_stable_regardless_of_key_order() -> None:
    a = hash_params({"name": "submit_booking_draft", "arguments": {"x": 1}})
    b = hash_params({"arguments": {"x": 1}, "name": "submit_booking_draft"})
    assert a == b


async def test_call_view_rpc_blocks_a_tool_not_on_the_view_allowlist() -> None:
    audit = AppAuditLog()
    with pytest.raises(AppRpcError):
        await call_view_rpc(
            session_id="s1",
            resource_uri="ui://booking/form",
            method="tools/call",
            params={"name": "confirm_booking", "arguments": {}},
            resource_server_url="http://127.0.0.1:1",  # never reached -- blocked before dispatch
            app_tool_config={"instance": None},  # type: ignore[typeddict-item]
            allowed_tools=frozenset({"submit_booking_draft"}),
            audit=audit,
        )
    entries = audit.for_session("s1")
    assert len(entries) == 1
    assert entries[0].decision == "blocked"
    assert entries[0].method == "tools/call"


async def test_call_view_rpc_blocks_an_unknown_method() -> None:
    audit = AppAuditLog()
    with pytest.raises(AppRpcError):
        await call_view_rpc(
            session_id="s1",
            resource_uri="ui://booking/form",
            method="prompts/list",  # not in the view's permitted method set at all
            params={},
            resource_server_url="http://127.0.0.1:1",
            app_tool_config={"instance": None},  # type: ignore[typeddict-item]
            allowed_tools=frozenset({"submit_booking_draft"}),
            audit=audit,
        )
    assert audit.for_session("s1")[0].decision == "blocked"
