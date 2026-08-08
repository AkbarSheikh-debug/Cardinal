/**
 * The (same-origin, not part of the MCP Apps spec) messages between the React host component
 * (`McpAppHost.tsx`, in the main app document) and the outer iframe's own page
 * (`outerEntry.ts`, loaded from `/mcp-outer.html`). Split from `protocol.ts` deliberately --
 * these are our own plumbing for handing an outer iframe its session/resource config and
 * surfacing view-originated events back up to React, not anything a spec-compliant client or
 * server ever sees.
 */

export interface HostBridgeInit {
  type: "cardinal-mcp-host/init";
  sessionId: string;
  resourceUri: string;
  toolName: string;
  toolInput: Record<string, unknown>;
  rpcEndpoint: string;
  theme: "light" | "dark";
}

export interface HostBridgeResize {
  type: "cardinal-mcp-host/resize";
  containerDimensions: { width: number; maxHeight: number };
}

export interface HostBridgeTeardown {
  type: "cardinal-mcp-host/teardown";
}

export type HostToOuterMessage = HostBridgeInit | HostBridgeResize | HostBridgeTeardown;

export interface OuterToHostEvent {
  type: "cardinal-mcp-host/event";
  event: "ready" | "message" | "open-link" | "submitted" | "error";
  payload: unknown;
}

export function isOuterToHostEvent(value: unknown): value is OuterToHostEvent {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { type?: unknown }).type === "cardinal-mcp-host/event"
  );
}

export function isHostToOuterMessage(value: unknown): value is HostToOuterMessage {
  if (typeof value !== "object" || value === null) return false;
  const type = (value as { type?: unknown }).type;
  return type === "cardinal-mcp-host/init" || type === "cardinal-mcp-host/resize" || type === "cardinal-mcp-host/teardown";
}
