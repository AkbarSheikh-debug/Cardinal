import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite + React 19 (PLAN-00 SS7). `/api` is proxied to the FastAPI backend in dev so the
// SSE/actions transport (PHASE-6 SS6, src/api/main.py) works without a second CORS story.
// `/mcp-apps` is PHASE-7's host-proxy endpoint -- the *only* thing the outer iframe ever calls.
//
// `allowedHosts` includes `localhost` explicitly alongside the Vite defaults: PHASE-7 SS5.1's
// dev cross-origin trick serves the sandbox proxy from whichever of `127.0.0.1`/`localhost` the
// host page *isn't* using, same port, same Vite server -- both hostnames have to resolve to
// this one dev server for that split to work.
// Shared between `server` and `preview` (PreviewOptions extends CommonServerOptions): gate 6.2
// already drives `npm run build && npm run preview` rather than the dev server (real build, no
// HMR noise), and gate 7 does the same -- `/mcp-apps` and the dual-hostname split have to work
// under `preview` too, or the gate would pass against a dev-only config that never ships.
//
// `CARDINAL_API_PORT` overrides the target port -- `make dev`/`docker compose` both run the
// product API on :8000 and this defaults to that, but `scripts/gate_phase7.py` starts its own,
// disposable backend on a different port and points here at it via this var. Discovered while
// building this phase: a `docker compose up` left running from earlier the same day was still
// bound to :8000, so a gate that assumed "something on :8000 must be mine" silently talked to a
// stale container with none of this phase's routes instead of failing loudly.
const API_PORT = process.env.CARDINAL_API_PORT || "8000";
const API_TARGET = `http://localhost:${API_PORT}`;
const PROXY = {
  "/sessions": API_TARGET,
  "/health": API_TARGET,
  "/adapters": API_TARGET,
  // A plain string entry here proxies by *prefix*, which also swallows P6's static 3D-asset
  // path `/models/powertrain/*.glb` (unrelated, older than this route) into a 404 -- the same
  // collision `web/nginx.conf`'s `location = /models` fix documents (D-057). `bypass` returning
  // the original path for anything that isn't the exact route hands it back to Vite's own
  // static/public-file serving instead of proxying it.
  "/models": {
    target: API_TARGET,
    bypass: (req: { url?: string }) => (req.url !== "/models" ? req.url : undefined),
  },
  "/mcp-apps": API_TARGET,
  "/demo": API_TARGET,
  // PLAN-02 P12. Both of these must also exist in `web/nginx.conf` or the container silently
  // serves `index.html` with a 200 for them and the login fetch parses HTML as JSON (D-057).
  "/auth": API_TARGET,
  // PLAN-02 P12/P15. Trailing slash, load-bearing: `"/seller"` would also swallow the *page*
  // navigation to `/seller` and hand the seller a JSON 409 instead of their console. Every
  // seller API route lives at `/seller/...` for exactly that reason (D-076).
  "/seller/": API_TARGET,
  // PLAN-02 P14. The trailing slash is load-bearing, not tidiness: Vite matches string proxy
  // keys with `startsWith`, so `"/cart"` would also swallow the *page* navigation to `/cart`
  // and hand the buyer a JSON 401 instead of the cart page. Every cart API route lives at
  // `/cart/...` for exactly this reason (D-076, `src/api/cart.py`'s docstring).
  "/cart/": API_TARGET,
  // PLAN-02 P16. Must exist here *and* in web/nginx.conf -- gate 16.13 derives the required
  // set from FastAPI's own route table and fails if either file is missing one.
  "/voice/": API_TARGET,
};
const ALLOWED_HOSTS = ["localhost", "127.0.0.1"];

// `sandboxOrigin()` (web/src/mcp-host/sandboxOrigin.ts) swaps `localhost` <-> `127.0.0.1` to
// get two distinct origins for the sandboxed MCP App iframe, on the assumption both names
// reach this same server. That's only true if this server actually listens on the IPv4
// loopback address -- Node's default bind for hostname `"localhost"` resolves via the OS
// resolver and, on a machine where that resolves to `::1` first (a real Windows default, not
// a misconfiguration), binds IPv6-only. `127.0.0.1` then connects to nothing, the sandboxed
// iframe fails to load, and the booking form/checkout renders blank. Binding explicitly here
// sidesteps the resolution order entirely: browsers fall back to whichever of `::1`/`127.0.0.1`
// actually accepts a connection (Happy Eyeballs, RFC 8305), so both hostnames keep working.
const DEV_HOST = "127.0.0.1";

export default defineConfig({
  plugins: [react()],
  server: {
    host: DEV_HOST,
    port: 5173,
    allowedHosts: ALLOWED_HOSTS,
    proxy: PROXY,
  },
  preview: {
    host: DEV_HOST,
    port: 4173,
    strictPort: true,
    allowedHosts: ALLOWED_HOSTS,
    proxy: PROXY,
  },
  build: {
    rollupOptions: {
      input: {
        main: "index.html",
        harness: "harness.html",
        mcpHostHarness: "mcp-host-harness.html",
        mcpOuter: "mcp-outer.html",
        mcpSandboxProxy: "mcp-sandbox-proxy.html",
      },
    },
  },
});
