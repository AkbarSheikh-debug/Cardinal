/**
 * The React-facing piece of the MCP Apps host (PHASE-7): a panel that mounts a fresh outer
 * `<iframe src="/mcp-outer.html">` per open and tears the whole nested frame tree down on close.
 * Always remounting rather than resetting internal state is what gate 7.7 (no leak after 20
 * open/close cycles) gets almost for free -- a removed iframe's realm (listeners, timers,
 * pending fetches inside it) is reclaimed by the browser, not by any cleanup code in this file
 * having to remember everything it started.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { isOuterToHostEvent, type HostToOuterMessage } from "./hostBridge";

export interface McpAppHostProps {
  sessionId: string;
  resourceUri: string;
  toolName: string;
  toolInput: Record<string, unknown>;
  rpcEndpoint?: string;
  onChatMessage?: (text: string) => void;
  onClose: () => void;
}

function detectTheme(): "light" | "dark" {
  if (typeof window === "undefined" || !window.matchMedia) return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function McpAppHost(props: McpAppHostProps): React.ReactElement {
  const { sessionId, resourceUri, toolName, toolInput, onChatMessage, onClose } = props;
  const rpcEndpoint = props.rpcEndpoint ?? `/mcp-apps/${sessionId}/rpc`;
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(false);
  const theme = useMemo(detectTheme, []);

  function postToOuter(message: HostToOuterMessage): void {
    iframeRef.current?.contentWindow?.postMessage(message, window.location.origin);
  }

  useEffect(() => {
    function handleMessage(event: MessageEvent): void {
      if (event.source !== iframeRef.current?.contentWindow || event.origin !== window.location.origin) return;
      if (!isOuterToHostEvent(event.data)) return;
      switch (event.data.event) {
        case "ready":
          setReady(true);
          break;
        case "message": {
          const payload = event.data.payload as { text?: string } | undefined;
          if (payload?.text) onChatMessage?.(payload.text);
          break;
        }
        case "error":
          // eslint-disable-next-line no-console
          console.error("MCP App error:", event.data.payload);
          break;
        default:
          break;
      }
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [onChatMessage]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      postToOuter({
        type: "cardinal-mcp-host/resize",
        containerDimensions: {
          width: Math.round(entry.contentRect.width),
          maxHeight: Math.round(entry.contentRect.height),
        },
      });
    });
    observer.observe(container);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  useEffect(() => {
    return () => postToOuter({ type: "cardinal-mcp-host/teardown" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleOuterLoad(): void {
    postToOuter({
      type: "cardinal-mcp-host/init",
      sessionId,
      resourceUri,
      toolName,
      toolInput,
      rpcEndpoint,
      theme,
    });
  }

  return (
    <div className="cardinal-mcp-app-host" data-testid="mcp-app-host" data-ready={ready}>
      <div className="cardinal-mcp-app-host-bar">
        <span>{toolName === "open_checkout" ? "Checkout" : "Booking form"}</span>
        <button type="button" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      <div className="cardinal-mcp-app-host-frame" ref={containerRef}>
        <iframe
          ref={iframeRef}
          title="MCP App"
          src="/mcp-outer.html"
          onLoad={handleOuterLoad}
          style={{ width: "100%", height: "100%", border: 0, display: "block" }}
        />
      </div>
    </div>
  );
}
