/**
 * Mirrors `src/mcp/apps/meta.py`'s `DEFAULT_CSP`/`effective_csp` exactly. Deliberately
 * duplicated rather than shared: Python and TypeScript can't share a module, and both sides
 * computing the *same* merge independently is what gate 7.2 is actually proving -- the host
 * enforces what the resource declared, not "the host enforces whatever this one function
 * returns." If these two ever drift, gate 7.2 is the thing that catches it.
 */

export const DEFAULT_CSP: Record<string, string> = {
  "default-src": "'none'",
  "script-src": "'self' 'unsafe-inline'",
  "style-src": "'self' 'unsafe-inline'",
  "img-src": "'self' data:",
  "media-src": "'self' data:",
  "connect-src": "'none'",
};

export function effectiveCsp(connectDomains: string[]): Record<string, string> {
  const csp = { ...DEFAULT_CSP };
  if (connectDomains.length > 0) {
    csp["connect-src"] = ["'self'", ...connectDomains].join(" ");
  }
  return csp;
}
