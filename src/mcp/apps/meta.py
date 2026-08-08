"""Shared `_meta.ui` shape for MCP App resources, and the CSP default (PHASE-7 SS5.4).

One helper so every `ui://` resource -- `booking-mcp` today, checkout in P8 -- builds `_meta`
and derives its enforced CSP the same way, rather than five call sites hand-rolling the same
dict and silently drifting apart.
"""

from __future__ import annotations

from typing import Any

#: PHASE-7 SS5.4's default, applied whenever a resource's own `_meta.ui.csp` omits a directive.
#: A missing directive is the strictest possible value, never an unset/permissive one -- that's
#: the gotcha the phase doc calls out by name: `connect-src 'none'` means a plain `fetch()`
#: silently does nothing unless the resource explicitly declares `connectDomains`.
DEFAULT_CSP: dict[str, str] = {
    "default-src": "'none'",
    "script-src": "'self' 'unsafe-inline'",
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data:",
    "media-src": "'self' data:",
    "connect-src": "'none'",
}


def resource_ui_meta(
    *, connect_domains: tuple[str, ...] = (), prefers_border: bool = False
) -> dict[str, Any]:
    """`_meta` for a `resources/list`/`resources/read` declaration (PHASE-7 SS4's jsonc example).

    `connect_domains` is the only thing a resource declares -- everything else in `DEFAULT_CSP`
    is fixed, so an App can widen `connect-src` for a genuine need but this call site can never
    accidentally loosen `script-src`/`default-src` too.
    """
    csp = {"connectDomains": list(connect_domains)}
    return {"ui": {"csp": csp, "prefersBorder": prefers_border}}


def effective_csp(connect_domains: tuple[str, ...] = ()) -> dict[str, str]:
    """The directives the host actually enforces for a resource declaring `connect_domains`.

    Both the sandbox proxy (which writes the `<meta http-equiv="Content-Security-Policy">` tag
    into the inner iframe's document) and gate 7.2 (which reads it back from the live DOM) must
    derive this the same way, or the gate is comparing two independently-typed policies instead
    of proving the host enforces what the resource declared.
    """
    csp = dict(DEFAULT_CSP)
    if connect_domains:
        csp["connect-src"] = " ".join(("'self'", *connect_domains))
    return csp


def csp_header_value(csp: dict[str, str]) -> str:
    return "; ".join(f"{directive} {value}" for directive, value in csp.items())
