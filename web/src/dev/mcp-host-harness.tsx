/**
 * Gate 7's target page: mounts `McpAppHost` directly from query params, with no live agent
 * session and no SSE involved -- the same isolation principle gate 6.2's `fixture-harness.tsx`
 * uses for A2UI, applied to the MCP Apps host. PHASE-7 §3's own build order asks for exactly
 * this: "get the double-iframe up... before wiring real booking logic," and a harness that
 * mounts the host straight from a URL is what lets `scripts/gate_phase7.py` drive that in
 * isolation against a real running `src.api.main:app` + `booking-mcp` HTTP server, without
 * needing `DEMO_MODE` or a live `ClaudeSDKClient` turn to get there.
 *
 * `?session=<id>&resourceUri=ui://booking/form&toolName=open_booking_form&toolInput=<json>`
 *
 * `window.__cardinalOpen()`/`__cardinalClose()` (gate 7.7's 20 open/close cycles) and the
 * `#canary` element (gate 7.8's "no layout shift in the surrounding surface", since the host
 * panel is a fixed-position overlay -- `#canary`'s position proves the rest of the page never
 * reflows) are test hooks on this harness page specifically, not on the product `App.tsx`.
 */
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { McpAppHost } from "../mcp-host/McpAppHost";
import "../styles.css";

declare global {
  interface Window {
    __cardinalOpen?: () => void;
    __cardinalClose?: () => void;
  }
}

function params(): { sessionId: string; resourceUri: string; toolName: string; toolInput: Record<string, unknown> } {
  const search = new URLSearchParams(window.location.search);
  let toolInput: Record<string, unknown> = {};
  const raw = search.get("toolInput");
  if (raw) {
    try {
      toolInput = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      toolInput = {};
    }
  }
  return {
    sessionId: search.get("session") ?? "gate7-session",
    resourceUri: search.get("resourceUri") ?? "ui://booking/form",
    toolName: search.get("toolName") ?? "open_booking_form",
    toolInput,
  };
}

function Harness(): React.ReactElement {
  const config = params();
  const [openCount, setOpenCount] = useState(1); // mounted once on load, matching a real open
  const [open, setOpen] = useState(true);

  window.__cardinalOpen = () => {
    setOpenCount((n) => n + 1);
    setOpen(true);
  };
  window.__cardinalClose = () => setOpen(false);

  return (
    <div data-testid="mcp-host-harness-root">
      <div id="canary" data-testid="canary" style={{ position: "absolute", top: 40, left: 40, width: 80, height: 20 }}>
        canary
      </div>
      {open && (
        <McpAppHost
          key={openCount}
          sessionId={config.sessionId}
          resourceUri={config.resourceUri}
          toolName={config.toolName}
          toolInput={config.toolInput}
          onClose={() => setOpen(false)}
          onChatMessage={(text) => {
            // Surfaced as a DOM attribute so Playwright can assert on it without a second
            // transport -- the harness never round-trips into a real session.
            document.body.dataset.lastChatMessage = text;
          }}
        />
      )}
    </div>
  );
}

const container = document.getElementById("root");
if (!container) {
  throw new Error("#root element not found");
}
createRoot(container).render(
  <StrictMode>
    <Harness />
  </StrictMode>,
);
