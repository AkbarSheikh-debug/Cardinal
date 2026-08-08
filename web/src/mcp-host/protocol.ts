/**
 * The MCP Apps wire protocol (PHASE-7 §5.2/§5.3), shared by every piece of `mcp-host/` --
 * one file so a revision bump (the doc's own risk note: "protocolVersion may move") touches one
 * place. Plain JSON-RPC 2.0 envelopes over `postMessage`, not a new transport.
 */

export const PROTOCOL_VERSION = "2026-01-26";

export const UI_INITIALIZE = "ui/initialize";

export interface JsonRpcRequest<M extends string = string, P = unknown> {
  jsonrpc: "2.0";
  id: number;
  method: M;
  params: P;
}

export interface JsonRpcNotification<M extends string = string, P = unknown> {
  jsonrpc: "2.0";
  method: M;
  params: P;
}

export interface JsonRpcResult<R = unknown> {
  jsonrpc: "2.0";
  id: number;
  result: R;
}

export interface JsonRpcError {
  jsonrpc: "2.0";
  id: number;
  error: { code: number; message: string; data?: unknown };
}

export type JsonRpcResponse<R = unknown> = JsonRpcResult<R> | JsonRpcError;
export type JsonRpcMessage = JsonRpcRequest | JsonRpcNotification | JsonRpcResponse;

export function isJsonRpcMessage(value: unknown): value is JsonRpcMessage {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  if (obj.jsonrpc !== "2.0") return false;
  return typeof obj.method === "string" || "result" in obj || "error" in obj;
}

export function isRequest(message: JsonRpcMessage): message is JsonRpcRequest {
  return "method" in message && "id" in message;
}

export function isNotification(message: JsonRpcMessage): message is JsonRpcNotification {
  return "method" in message && !("id" in message);
}

export function isResponse(message: JsonRpcMessage): message is JsonRpcResponse {
  return "result" in message || "error" in message;
}

// -- Handshake (§5.2) ----------------------------------------------------------------------

export interface AppCapabilities {
  availableDisplayModes: DisplayMode[];
}

export type DisplayMode = "inline" | "fullscreen" | "pip";

export interface UiInitializeParams {
  appCapabilities: AppCapabilities;
}

export interface HostContext {
  theme: "light" | "dark";
  styles: { variables: Record<string, string> };
  displayMode: DisplayMode;
  containerDimensions: { width: number; maxHeight: number };
  locale: string;
  platform: "web";
}

export interface UiInitializeResult {
  protocolVersion: string;
  hostCapabilities: Record<string, never>;
  hostContext: HostContext;
}

// -- Host -> view notifications (§5.3) ------------------------------------------------------

export interface ToolInputParams {
  toolName: string;
  toolInput: Record<string, unknown>;
}

export interface ToolResultParams {
  toolName: string;
  result: unknown;
}

export interface SizeChangedParams {
  containerDimensions: { width: number; maxHeight: number };
}

export const HOST_NOTIFICATIONS = {
  toolInput: "ui/notifications/tool-input",
  toolInputPartial: "ui/notifications/tool-input-partial",
  toolResult: "ui/notifications/tool-result",
  toolCancelled: "ui/notifications/tool-cancelled",
  sizeChanged: "ui/notifications/size-changed",
  resourceTeardown: "ui/resource-teardown",
} as const;

// -- View -> host requests (§5.3) -----------------------------------------------------------

export const VIEW_REQUESTS = {
  toolsCall: "tools/call",
  resourcesRead: "resources/read",
  openLink: "ui/open-link",
  message: "ui/message",
  requestDisplayMode: "ui/request-display-mode",
  updateModelContext: "ui/update-model-context",
} as const;

//: Fire-and-forget (no response expected), unlike everything in VIEW_REQUESTS.
export const VIEW_NOTIFICATION_MESSAGE = "notifications/message";

// -- Sandbox-internal (host outer <-> sandbox proxy <-> inner; §5.1) ------------------------

export const SANDBOX_NOTIFICATIONS = {
  /** Outer -> sandbox proxy: the fetched resource HTML + its declared CSP, ready to render. */
  resourceReady: "ui/notifications/sandbox-resource-ready",
} as const;

export interface SandboxResourceReadyParams {
  html: string;
  csp: Record<string, string>;
  resourceUri: string;
}
