/**
 * The `/cart/*` client -- PLAN-02 P14.
 *
 * Every route lives one level below `/cart` on purpose. `/cart` is also the page this app
 * navigates to, and neither nginx nor Vite can tell a navigation from a `fetch()` by path
 * alone -- so the API keeps to `/cart/items`, `/cart/checkout`, `/cart/count` and the bare
 * path stays the SPA's (D-076, `src/api/cart.py`'s docstring, `web/vite.config.ts`).
 *
 * `credentials: "include"` on every call, for the same reason `auth/api.ts` does it: the cart
 * is scoped to whoever the httpOnly session cookie says you are. There is no account id in any
 * of these signatures and no way to supply one -- which is what makes cross-account isolation
 * (gate 14.11) a property of the route shape rather than a check.
 */

export type OfferType = "buy" | "rent" | "both";

export interface Payee {
  legal_name: string;
  display_name: string;
  address: string;
  city: string;
  country: string;
  phone: string;
  verification_status: string;
  /** True when the payee is unverified or still pending -- the UI must say so, not go quiet. */
  needs_flag: boolean;
  one_line: string;
}

export interface CartLine {
  item_id: string;
  source: string;
  source_id: string;
  offer_type: OfferType;
  added_at: string;
  /** False once the listing is withdrawn -- checkout refuses it and the line says why. */
  available: boolean;
  headline: string | null;
  condition: string | null;
  price: { amount: string; currency: string } | null;
  payee: Payee | null;
}

export interface CartPayload {
  count: number;
  items: CartLine[];
  checkout_is_single_item: boolean;
}

export class CartError extends Error {}

async function detailOf(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    return typeof body?.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

async function json<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw new CartError(await detailOf(response, fallback));
  return response.json() as Promise<T>;
}

export async function fetchCart(): Promise<CartPayload> {
  return json(
    await fetch("/cart/items", { credentials: "include" }),
    "could not read your cart",
  );
}

/**
 * `count` alone, for the header badge. Answers 0 rather than 401 for a signed-out visitor, so
 * the badge has one code path instead of a "not signed in" branch that renders as an error.
 */
export async function fetchCartCount(): Promise<number> {
  try {
    const response = await fetch("/cart/count", { credentials: "include" });
    if (!response.ok) return 0;
    const body = await response.json();
    return typeof body?.count === "number" ? body.count : 0;
  } catch {
    return 0;
  }
}

export async function addToCart(
  source: string,
  sourceId: string,
  offerType: OfferType,
): Promise<CartPayload> {
  const response = await fetch("/cart/items", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ source, source_id: sourceId, offer_type: offerType }),
  });
  return json(response, "could not add that car to your cart");
}

export async function removeCartItem(itemId: string): Promise<CartPayload> {
  const response = await fetch(`/cart/items/${itemId}`, {
    method: "DELETE",
    credentials: "include",
  });
  return json(response, "could not remove that line");
}

/**
 * Opens the *booking form* MCP App for one line, in this browser's own agent session.
 *
 * It returns as soon as the App has been pushed onto the session's SSE stream -- the App
 * itself then runs the existing, already-gated P7/P8 sequence, and nothing on this page mints
 * a gesture token or goes anywhere near `confirm_booking` (CONSTITUTION I.2, gate 14.6).
 */
export async function startCheckout(sessionId: string, itemId: string): Promise<void> {
  const response = await fetch("/cart/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ session_id: sessionId, item_id: itemId }),
  });
  if (!response.ok) throw new CartError(await detailOf(response, "could not start checkout"));
}
