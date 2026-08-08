/**
 * Where the sandbox proxy lives, relative to wherever the host page is running (PHASE-7 §5.1's
 * "in dev, a second port is not a different origin -- use a distinct hostname" note).
 *
 * Production: a genuinely different registrable domain (`sandbox.cardinal.app` vs
 * `cardinal.app`), per the phase doc. Dev: `127.0.0.1` and `localhost` are two different origins
 * for the same loopback address, resolved locally by the OS with no DNS lookup and no `/etc/hosts`
 * edit required -- whichever one the host page is running on, the sandbox runs on the other, same
 * port, same Vite server. One function, so a prod deploy only ever touches this file.
 */

export function sandboxOrigin(): string {
  const { protocol, hostname, port } = window.location;
  const sandboxHost =
    hostname === "127.0.0.1" ? "localhost" : hostname === "localhost" ? "127.0.0.1" : `sandbox.${hostname}`;
  return `${protocol}//${sandboxHost}${port ? `:${port}` : ""}`;
}
