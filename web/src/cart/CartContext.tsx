/**
 * One place that knows what is in the cart -- PLAN-02 P14.
 *
 * Mounted above the router next to `SessionProvider`, because the badge lives in the buyer
 * header on *every* buyer route and the `/cart` page reads the same state: two independent
 * fetches would let the badge and the page disagree, which is the one thing a cart must never
 * do.
 *
 * `add()` returns the fresh payload the POST answered with rather than re-fetching. The count
 * the badge shows is therefore the count the server computed for that exact mutation -- gate
 * 14.1's "updates without a reload" holds because there is no second round-trip to lose.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  addToCart as apiAdd,
  fetchCart,
  fetchCartCount,
  removeCartItem as apiRemove,
  type CartPayload,
  type OfferType,
} from "./api";
import { useSession } from "../auth/SessionContext";

interface CartValue {
  count: number;
  /** `null` until the full cart has been read -- the badge only ever needs `count`. */
  cart: CartPayload | null;
  /** The last add/remove failure, in the buyer's words. Cleared by the next successful one. */
  error: string | null;
  refresh: () => Promise<void>;
  add: (source: string, sourceId: string, offerType: OfferType) => Promise<void>;
  remove: (itemId: string) => Promise<void>;
}

const CartContext = createContext<CartValue | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const { status, session } = useSession();
  const [cart, setCart] = useState<CartPayload | null>(null);
  const [count, setCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback((payload: CartPayload) => {
    setCart(payload);
    setCount(payload.count);
    setError(null);
  }, []);

  const refresh = useCallback(async () => {
    // A seller (or nobody) has no cart. Asking for one would 403 and paint an error into a
    // header that has nothing to do with them.
    if (status !== "authenticated" || session?.account.role !== "buyer") {
      setCart(null);
      setCount(0);
      return;
    }
    try {
      apply(await fetchCart());
    } catch {
      // Fall back to the cheap endpoint: a badge that shows a stale-but-real number beats a
      // header that breaks because one enrichment lookup failed.
      setCount(await fetchCartCount());
    }
  }, [status, session, apply]);

  const add = useCallback(
    async (source: string, sourceId: string, offerType: OfferType) => {
      // Named before the request rather than after it. `refresh` has always skipped a cart it
      // knows cannot exist; `add` fired anyway and let the server answer 403 with "this route
      // is for buyer accounts" -- accurate, and no help to someone who did not know which
      // account they were signed in as. A seller can be shown a card with an add button on
      // it (the agent renders the same canvas for both), so this is reachable, not defensive.
      if (status !== "authenticated" || !session) {
        setError("Your session has expired — sign in again to use the cart.");
        return;
      }
      if (session.account.role !== "buyer") {
        setError(
          `The cart belongs to buyer accounts, and you are signed in as a seller (${session.account.email}). Sign out and sign back in as a buyer to add cars.`,
        );
        return;
      }
      try {
        apply(await apiAdd(source, sourceId, offerType));
      } catch (err) {
        setError(err instanceof Error ? err.message : "could not add that car");
      }
    },
    [apply, status, session],
  );

  const remove = useCallback(
    async (itemId: string) => {
      try {
        apply(await apiRemove(itemId));
      } catch (err) {
        setError(err instanceof Error ? err.message : "could not remove that line");
      }
    },
    [apply],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ count, cart, error, refresh, add, remove }),
    [count, cart, error, refresh, add, remove],
  );
  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartValue {
  const value = useContext(CartContext);
  if (!value) throw new Error("useCart must be used inside a <CartProvider>");
  return value;
}
