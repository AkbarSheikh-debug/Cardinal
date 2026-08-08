/**
 * The sandbox proxy shell (PHASE-7 §5.1): a small trusted page served from the *sandbox*
 * origin, whose only two jobs are (1) turn one `ui/notifications/sandbox-resource-ready`
 * message into a same-origin inner iframe carrying the resource's CSP, and (2) forward every
 * other message verbatim between the host (its cross-origin parent) and that inner iframe --
 * "the proxy forwards messages between host and view, except `ui/notifications/sandbox-*`,
 * which it consumes."
 *
 * Deliberately dumb: this file never interprets a forwarded message's `method`/`params`, only
 * its envelope-level origin/source. Interpreting content is the host's job (`outerEntry.ts`) and
 * the App's job (`booking_form.html`) -- a relay that has to understand what it's relaying is a
 * relay that can be tricked by what it (mis)understands.
 *
 * Trust-on-first-use for the host origin: the first sender to speak is remembered and every
 * later message must match it. There's nothing to steal on this origin (no cookies, no session,
 * no secrets -- CONSTITUTION II.5's whole point), so TOFU's only job is rejecting a *second*,
 * different origin from hijacking an in-progress relay, not authenticating the first one.
 */
import { SANDBOX_NOTIFICATIONS, HOST_NOTIFICATIONS, type SandboxResourceReadyParams } from "./protocol";

let trustedHostOrigin: string | null = null;
let innerFrameEl: HTMLIFrameElement | null = null;
let innerWindow: Window | null = null;
let innerObjectUrl: string | null = null;

function cspHeaderValue(csp: Record<string, string>): string {
  return Object.entries(csp)
    .map(([directive, value]) => `${directive} ${value}`)
    .join("; ");
}

function withCspMetaTag(html: string, csp: Record<string, string>): string {
  const tag = `<meta http-equiv="Content-Security-Policy" content="${cspHeaderValue(csp).replace(/"/g, "&quot;")}">`;
  if (/<head[^>]*>/i.test(html)) {
    return html.replace(/<head[^>]*>/i, (match) => `${match}${tag}`);
  }
  // No <head> in the resource's HTML: prepend one. The CSP meta tag must be present before any
  // <script>/<style> it's meant to restrict, so it cannot simply be appended at the end.
  return `<head>${tag}</head>${html}`;
}

function teardownInner(): void {
  if (innerFrameEl) {
    innerFrameEl.remove();
    innerFrameEl = null;
  }
  innerWindow = null;
  if (innerObjectUrl) {
    URL.revokeObjectURL(innerObjectUrl);
    innerObjectUrl = null;
  }
}

function mountInner(params: SandboxResourceReadyParams): void {
  teardownInner();
  const blob = new Blob([withCspMetaTag(params.html, params.csp)], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  innerObjectUrl = url;

  const iframe = document.createElement("iframe");
  // No `allow-same-origin` omission trick here: the resource genuinely *is* same-origin as
  // this proxy (a blob: URL inherits its creator's origin), so `allow-same-origin` reflects
  // reality rather than granting anything extra. `allow-scripts`/`allow-forms` are what the
  // booking form actually needs; no allow-popups, no allow-top-navigation.
  iframe.setAttribute("sandbox", "allow-scripts allow-forms allow-same-origin");
  iframe.setAttribute("data-resource-uri", params.resourceUri);
  iframe.style.cssText = "width:100%;height:100%;border:0;display:block;";
  iframe.addEventListener("load", () => {
    innerWindow = iframe.contentWindow;
  });
  iframe.src = url;
  document.body.appendChild(iframe);
  innerFrameEl = iframe;
}

window.addEventListener("message", (event: MessageEvent) => {
  if (innerWindow && event.source === innerWindow) {
    if (trustedHostOrigin) window.parent.postMessage(event.data, trustedHostOrigin);
    return;
  }

  if (trustedHostOrigin === null) {
    trustedHostOrigin = event.origin;
  } else if (event.origin !== trustedHostOrigin) {
    return; // a second, different origin trying to speak mid-session -- ignored, not answered.
  }

  const message = event.data as { method?: string; params?: unknown } | null;
  if (message?.method === SANDBOX_NOTIFICATIONS.resourceReady) {
    mountInner(message.params as SandboxResourceReadyParams);
    return;
  }
  if (message?.method === HOST_NOTIFICATIONS.resourceTeardown) {
    teardownInner();
    return;
  }
  if (innerWindow) {
    innerWindow.postMessage(event.data, window.location.origin);
  }
});

// The proxy is ready the instant its script runs -- nothing here depends on module load order
// or a DOM element beyond <body>, so there's no separate "ready" signal to emit.
