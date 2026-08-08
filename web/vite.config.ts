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
};
const ALLOWED_HOSTS = ["localhost", "127.0.0.1"];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts: ALLOWED_HOSTS,
    proxy: PROXY,
  },
  preview: {
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
