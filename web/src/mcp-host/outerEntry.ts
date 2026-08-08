/**
 * The outer iframe (PHASE-7 SS5.1): same origin as the host page, holds the session, and is the
 * *only* browser context that ever calls our backend. Everything a view asks for --
 * `tools/call`, `resources/read` -- is proxied through `POST /mcp-apps/{session}/rpc`
 * (`src/api/main.py`), never reached directly; `ui/initialize`, `ui/open-link`,
 * `ui/request-display-mode` and `ui/update-model-context` are answered here, host-side, with no
 * server round-trip at all.
 *
 * Loaded as `/mcp-outer.html`, not part of the main React bundle, so this page's own CSP can
 * stay minimal regardless of what the product app needs (defense in depth on our *own* origin,
 * not just the sandbox one).
 */
import {
  HOST_NOTIFICATIONS,
  SANDBOX_NOTIFICATIONS,
  UI_INITIALIZE,
  VIEW_NOTIFICATION_MESSAGE,
  VIEW_REQUESTS,
  PROTOCOL_VERSION,
  type HostContext,
  type JsonRpcMessage,
  type UiInitializeParams,
  type UiInitializeResult,
} from "./protocol";
import { RpcChannel } from "./rpcChannel";
import { sandboxOrigin } from "./sandboxOrigin";
import { effectiveCsp } from "./csp";
import {
  isHostToOuterMessage,
  type HostBridgeInit,
  type HostToOuterMessage,
  type OuterToHostEvent,
} from "./hostBridge";

interface Config {
  sessionId: string;
  resourceUri: string;
  toolName: string;
  toolInput: Record<string, unknown>;
  rpcEndpoint: string;
  theme: "light" | "dark";
}

let config: Config | null = null;
let sandboxFrame: HTMLIFrameElement | null = null;
let sandboxWindow: Window | null = null;
let sandboxOriginValue = "";
let toolInputSent = false;
let lastContainerDimensions = { width: 660, maxHeight: 520 };

/** Test-observability only (gate 7.5's ordering check) -- always present, never gated behind a
 * test flag, since it's cheap and this is *our* trusted shell, not third-party App content. */
declare global {
  interface Window {
    __cardinalHostDebug?: { initRespondedAt: number | null; toolInputSentAt: number | null };
  }
}
window.__cardinalHostDebug = { initRespondedAt: null, toolInputSentAt: null };

function postToHost(event: OuterToHostEvent["event"], payload: unknown): void {
  const message: OuterToHostEvent = { type: "cardinal-mcp-host/event", event, payload };
  window.parent.postMessage(message, window.location.origin);
}

function sendToSandbox(message: JsonRpcMessage): void {
  if (!sandboxWindow) return;
  sandboxWindow.postMessage(message, sandboxOriginValue);
}

const sandboxChannel = new RpcChannel(sendToSandbox);

async function callBackendRpc(method: string, params: unknown): Promise<unknown> {
  if (!config) throw new Error("outer received a view request before init");
  const response = await fetch(config.rpcEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resourceUri: config.resourceUri, method, params }),
  });
  const body = (await response.json().catch(() => ({}))) as { result?: unknown; detail?: string };
  if (!response.ok) {
    throw new Error(body.detail ?? `${method} failed with HTTP ${response.status}`);
  }
  return body.result;
}

function buildInitializeResult(_params: UiInitializeParams): UiInitializeResult {
  const theme = config?.theme ?? "light";
  const hostContext: HostContext = {
    theme,
    styles: {
      variables:
        theme === "dark"
          ? { "--color-text-primary": "#E8EDE9", "--color-surface": "#1A1A1A" }
          : { "--color-text-primary": "#1A1A1A", "--color-surface": "#FFFFFF" },
    },
    // [SCALE] per PHASE-7 §2: fullscreen/pip aren't implemented, so this host never reports
    // (or switches to) anything but "inline" -- an App can still *ask* via
    // ui/request-display-mode, it just always gets told no.
    displayMode: "inline",
    containerDimensions: lastContainerDimensions,
    locale: navigator.language || "en-GB",
    platform: "web",
  };
  return { protocolVersion: PROTOCOL_VERSION, hostCapabilities: {}, hostContext };
}

function sendToolInputOnce(): void {
  if (toolInputSent || !config) return;
  toolInputSent = true;
  sandboxChannel.notify(HOST_NOTIFICATIONS.toolInput, { toolName: config.toolName, toolInput: config.toolInput });
  if (window.__cardinalHostDebug) window.__cardinalHostDebug.toolInputSentAt = performance.now();
}

sandboxChannel.onRequest(VIEW_REQUESTS.toolsCall, (params) => callBackendRpc("tools/call", params));
sandboxChannel.onRequest(VIEW_REQUESTS.resourcesRead, (params) => callBackendRpc("resources/read", params));
sandboxChannel.onRequest(VIEW_REQUESTS.message, (params) => {
  postToHost("message", params);
  return { acknowledged: true };
});
sandboxChannel.onRequest(VIEW_REQUESTS.openLink, (params) => {
  postToHost("open-link", params);
  return { opened: false, reason: "not implemented" };
});
sandboxChannel.onRequest(VIEW_REQUESTS.requestDisplayMode, () => ({ displayMode: "inline" }));
sandboxChannel.onRequest(VIEW_REQUESTS.updateModelContext, () => ({ acknowledged: true }));
sandboxChannel.onNotification(VIEW_NOTIFICATION_MESSAGE, (params) => {
  // The one shape this fire-and-forget logging notification is treated specially: a CSP
  // violation the App observed on itself (gate 7.3/7.10 -- CSP blocks the fetch client-side,
  // where our server-side audit log would otherwise never learn it happened at all). Recorded
  // through the same `/mcp-apps/*/rpc` endpoint and the same `AppAuditLog` as everything else,
  // as a `blocked` entry, rather than a second, parallel logging mechanism.
  const data = params as { blocked?: boolean; blockedUri?: string; violatedDirective?: string } | undefined;
  if (data?.blocked) {
    void callBackendRpc("csp/violation", data).catch(() => {
      /* best-effort -- a failed *log* of a blocked fetch shouldn't itself surface as an error */
    });
  }
});

/** `ui/initialize` is handled outside `sandboxChannel` on purpose: the handshake response and
 * the one-time `tool-input` notification that follows it have to leave in that exact order, and
 * `RpcChannel`'s generic request/response flow doesn't expose a "do this right after replying"
 * hook. Two back-to-back `postMessage` calls from the same sender are delivered in the order
 * sent, so this is the whole ordering guarantee gate 7.5 needs.
 */
function handleInitializeRequest(id: number, params: unknown): void {
  const result = buildInitializeResult(params as UiInitializeParams);
  sendToSandbox({ jsonrpc: "2.0", id, result });
  if (window.__cardinalHostDebug) window.__cardinalHostDebug.initRespondedAt = performance.now();
  sendToolInputOnce();
  postToHost("ready", {});
}

async function bootstrapSandbox(): Promise<void> {
  if (!config) return;
  try {
    const raw = (await callBackendRpc("resources/read", { uri: config.resourceUri })) as {
      contents?: { text?: string; mimeType?: string; _meta?: { ui?: { csp?: { connectDomains?: string[] } } } }[];
    };
    const first = raw.contents?.[0];
    const html = first?.text ?? "<p>Empty resource.</p>";
    const csp = effectiveCsp(first?._meta?.ui?.csp?.connectDomains ?? []);
    sendToSandbox({
      jsonrpc: "2.0",
      method: SANDBOX_NOTIFICATIONS.resourceReady,
      params: { html, csp, resourceUri: config.resourceUri },
    });
  } catch (err) {
    postToHost("error", { message: err instanceof Error ? err.message : String(err) });
  }
}

function handleInit(init: HostBridgeInit): void {
  config = {
    sessionId: init.sessionId,
    resourceUri: init.resourceUri,
    toolName: init.toolName,
    toolInput: init.toolInput,
    rpcEndpoint: init.rpcEndpoint,
    theme: init.theme,
  };
  sandboxOriginValue = sandboxOrigin();
  sandboxFrame = document.createElement("iframe");
  sandboxFrame.style.cssText = "width:100%;height:100%;border:0;display:block;";
  sandboxFrame.addEventListener("load", () => {
    sandboxWindow = sandboxFrame?.contentWindow ?? null;
    void bootstrapSandbox();
  });
  sandboxFrame.src = `${sandboxOriginValue}/mcp-sandbox-proxy.html`;
  document.body.appendChild(sandboxFrame);
}

function handleHostBridgeMessage(message: HostToOuterMessage): void {
  if (message.type === "cardinal-mcp-host/init") {
    handleInit(message);
  } else if (message.type === "cardinal-mcp-host/resize") {
    lastContainerDimensions = message.containerDimensions;
    sandboxChannel.notify(HOST_NOTIFICATIONS.sizeChanged, { containerDimensions: message.containerDimensions });
  } else if (message.type === "cardinal-mcp-host/teardown") {
    sandboxChannel.notify(HOST_NOTIFICATIONS.resourceTeardown, {});
    sandboxChannel.cancelPending("resource torn down");
  }
}

function handleFromSandbox(data: unknown): void {
  const message = data as { method?: string; id?: number; params?: unknown } | null;
  if (message?.method === UI_INITIALIZE && typeof message.id === "number") {
    handleInitializeRequest(message.id, message.params);
    return;
  }
  void sandboxChannel.handleIncoming(data as JsonRpcMessage);
}

window.addEventListener("message", (event: MessageEvent) => {
  if (event.source === window.parent) {
    if (event.origin === window.location.origin && isHostToOuterMessage(event.data)) {
      handleHostBridgeMessage(event.data);
    }
    return;
  }
  if (sandboxWindow && event.source === sandboxWindow && event.origin === sandboxOriginValue) {
    handleFromSandbox(event.data);
  }
});

// No separate "outer script loaded" signal: React already learns that from the outer
// <iframe>'s own native `load` event (which is what triggers it to send `init` in the first
// place) and sends `cardinal-mcp-host/init` in response -- see `McpAppHost.tsx`. "ready" here
// is reserved for the more useful signal: the *view* has completed its own `ui/initialize`
// handshake, not merely that this shell's script has started running.
