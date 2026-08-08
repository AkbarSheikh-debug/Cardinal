# PHASE 7 — MCP Apps

**Owns:** the MCP Apps host. The hardest single component in the build, and the one almost nobody
else will do properly.

A2UI (P6) is *our* agent drawing into *our* origin. MCP Apps are a *third party's* HTML running
inside a sandbox we control. Same screen, completely different trust model. Conflating them is the
mistake.

---

## 1. Objective

A spec-compliant MCP Apps host — cross-origin sandbox, CSP enforcement, full JSON-RPC surface,
auditable — rendering the booking form served by `booking-mcp`.

## 2. Scope

### In
- `[MVP]` Double-iframe sandbox with origin isolation
- `[MVP]` CSP derivation and enforcement from resource `_meta.ui.csp`
- `[MVP]` `ui/initialize` handshake + `hostContext`
- `[MVP]` Host→view notification set
- `[MVP]` View→host request set, proxied to the MCP server
- `[MVP]` RPC audit log
- `[MVP]` `ui://booking/form` — the form-fill App (brief requirement R3)
- `[SCALE]` `ui/request-display-mode` — fullscreen / pip
- `[SCALE]` Theme + style-variable propagation from host
- `[SCALE]` `ui/update-model-context` so the App can inform later turns

### Out
- Checkout — P8. Same host, different App, and its invariants are commerce invariants.

---

## 3. Build it in this order

The temptation is to wire the booking logic and the host together. Don't — you'll be debugging two
unfamiliar things at once.

1. **Hardcoded HTML, no MCP.** Get the double-iframe up, get `postMessage` flowing both ways, get
   the handshake completing. One afternoon.
2. **Add CSP.** Verify a deliberately-blocked `fetch` actually fails and gets logged.
3. **Add the MCP server.** Serve the same hardcoded HTML through `resources/read`.
4. **Only then** build the real form.

Each step is independently verifiable. Skipping to step 4 means a failure could be in any of four
layers.

---

## 4. Server side

```jsonc
// resource declaration
{
  "uri": "ui://booking/form",
  "name": "Booking form",
  "mimeType": "text/html;profile=mcp-app",
  "_meta": { "ui": {
    "csp": { "connectDomains": [] },
    "prefersBorder": true
  }}
}

// tool bound to it
{
  "name": "open_booking_form",
  "_meta": { "ui": {
    "resourceUri": "ui://booking/form",
    "visibility": ["model", "app"]
  }}
}
```

Content is served via `resources/read` returning `mimeType: "text/html;profile=mcp-app"`.

Capability negotiation on initialize: the client advertises
`capabilities.extensions["io.modelcontextprotocol/ui"] = { mimeTypes: ["text/html;profile=mcp-app"] }`.

---

## 5. Host side — the actual work

### 5.1 Double-iframe

Required by the spec for web hosts, and it's the whole security story:

```
host page (our origin)
 └─ outer iframe (our origin) ........ MCP proxy; holds the session, forwards RPC
     └─ sandbox proxy iframe (DIFFERENT origin) ... loads untrusted HTML under CSP
         └─ inner iframe (same origin as proxy) ... receives HTML via
                                                    ui/notifications/sandbox-resource-ready
```

The proxy forwards messages between host and view, **except** `ui/notifications/sandbox-*`, which
it consumes. Serve the sandbox origin from a genuinely different host in production
(`sandbox.cardinal.app`); in dev, a second port is *not* a different origin for CSP purposes — use a
distinct hostname via `/etc/hosts` or a wildcard DNS service. This trips everyone once.

### 5.2 Handshake

```jsonc
// view → host
{"jsonrpc":"2.0","id":1,"method":"ui/initialize",
 "params":{"appCapabilities":{"availableDisplayModes":["inline","fullscreen"]}}}

// host → view
{"result":{
  "protocolVersion":"2026-01-26",
  "hostCapabilities":{},
  "hostContext":{
    "theme":"dark",
    "styles":{"variables":{"--color-text-primary":"#E8EDE9"}},
    "displayMode":"inline",
    "containerDimensions":{"width":660,"maxHeight":520},
    "locale":"en-GB","platform":"web"}}}
```

Propagating `theme` and `styles` is what stops the App looking pasted-on. Worth the hour.

### 5.3 Message surface

**Host → view (notifications):** `ui/notifications/tool-input` (once, after init),
`tool-input-partial` (streaming, 0..n), `tool-result`, `tool-cancelled`, `size-changed`,
`ui/resource-teardown`.

**View → host (requests):** `tools/call`, `resources/read`, `ui/open-link`, `ui/message`,
`ui/request-display-mode`, `ui/update-model-context`, `notifications/message`.

`tools/call` from the view is proxied through the host to the MCP server — **the view never talks to
the server directly.** That's what makes the audit log complete and the CSP meaningful.

### 5.4 CSP

Default when `ui.csp` is omitted:

```
default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';
img-src 'self' data:; media-src 'self' data:; connect-src 'none';
```

> **The gotcha that costs an evening:** `connect-src 'none'` and `img-src 'self' data:` mean a 3D
> viewer, a remote image, or a `fetch` inside an MCP App **will silently not work**. This is why the
> 3D layer lives in A2UI (our origin, P6) and MCP Apps are restricted to forms and checkout. If an
> App genuinely needs a remote asset, declare it in `resourceDomains` — never widen the default.

### 5.5 Audit log

Every view-initiated RPC is logged: timestamp, session, resource URI, method, params hash, decision
(allowed/blocked), and result status. The spec requires auditability; it also happens to be a
compelling slide, and in production it's the artifact you hand a compliance reviewer.

---

## 6. The booking App

`ui://booking/form` — buyer/renter details, dates, collection location, add-ons.

Behaviour that makes it feel agent-native rather than a bolted-on form:

- **Pre-filled from interview memory**, arriving via `ui/notifications/tool-input`. Pre-filled
  fields are visually distinguished (dashed outline in the preview) so the user can see what the
  agent assumed and correct it.
- **Submission is view-initiated**: `tools/call → submit_booking_draft`, `visibility: ["app"]`.
- **`ui/message`** lets the App push a line into the chat ("Collection date changed to 12 Sept") so
  the conversation stays coherent with what the user did in the form.

The App is plain HTML + inline CSS/JS — no framework, no build step, no external requests. Under
`script-src 'self' 'unsafe-inline'` with `connect-src 'none'`, that's not a limitation, it's the
only thing that works.

---

## 7. Exit gate

`scripts/gate_phase7.py` (Playwright-driven):

| # | Criterion |
|---|---|
| 7.1 | Inner iframe's origin ≠ host origin (asserted from the browser, not from config) |
| 7.2 | CSP header on the inner document matches the resource's `_meta.ui.csp`, with defaults applied where omitted |
| 7.3 | A `fetch()` to an undeclared domain from inside the App **fails** and appears in the audit log as `blocked` |
| 7.4 | `ui/initialize` completes; `hostContext.theme` reaches the App and visibly applies |
| 7.5 | `ui/notifications/tool-input` delivers pre-fill exactly once, after init |
| 7.6 | `tools/call` from the view reaches the MCP server **through the host proxy** — direct view→server traffic is impossible (asserted by network trace) |
| 7.7 | `ui/resource-teardown` removes the iframe and releases listeners; no leak after 20 open/close cycles |
| 7.8 | `size-changed` resizes the container without layout shift in the surrounding A2UI surface |
| 7.9 | Audit log contains one entry per view-initiated RPC, with no gaps, for a full booking flow |
| 7.10 | The App renders and functions with JavaScript's network access fully blocked (no silent dependency on egress) |

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Sandbox origin misconfigured in dev; CSP appears to work but doesn't | Gate 7.1 asserts from the browser. Use a real distinct hostname in dev, not a second port. |
| Handshake races — App renders before `tool-input` arrives | App must render an empty/loading state and populate on notification. Gate 7.5 checks ordering. |
| Spec is young; `2026-01-26` revision may move | Version-pin `protocolVersion`; keep all host logic in `web/src/mcp-host/` so a revision bump is one directory |
| Building host + booking logic simultaneously | The four-step order in §3. Non-negotiable. |
| iframe leaks across many open/close cycles | Gate 7.7 |
