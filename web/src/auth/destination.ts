/**
 * Where a signed-in account belongs — the single answer, because there are two places that
 * decide it and they raced.
 *
 * `LoginPage.onVerify` navigates once the code is accepted. But `refresh()` flips the session to
 * authenticated first, and the moment it does, `LoginRoute` re-renders and redirects an
 * already-signed-in visitor away from the form. Which of the two lands is a microtask-ordering
 * detail, and the observed winner was `LoginRoute` — so a buyer bounced to `/login` from `/cart`
 * arrived at `/chat` regardless of what `LoginPage` asked for.
 *
 * Rather than try to win the race, both callers now compute the same destination from the same
 * `location`, and whichever one runs is right.
 */
import type { Location } from "react-router-dom";
import type { AccountRole } from "./api";

/** The route a role owns when there is nowhere more specific to go. */
export function homeFor(role: AccountRole): string {
  return role === "seller" ? "/seller" : "/chat";
}

/**
 * `RequireRole` stashes the path a visitor was trying to reach in `location.state.from`; this
 * honours it, falling back to the role's home.
 *
 * Only same-origin absolute paths are accepted, and never `/login` itself — routing state that
 * can point anywhere is an open redirect waiting to be found, and one that can point back at the
 * form is a loop.
 */
export function destinationAfterSignIn(role: AccountRole, location: Location): string {
  const home = homeFor(role);
  const from = (location.state as { from?: unknown } | null)?.from;
  if (typeof from !== "string" || !from.startsWith("/") || from.startsWith("//")) return home;
  return from === "/login" ? home : from;
}
