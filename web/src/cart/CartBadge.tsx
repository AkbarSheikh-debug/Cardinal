/**
 * The cart control in the buyer header -- PLAN-02 P14.
 *
 * On every buyer route, because the count is the one piece of state that has to stay true
 * while the buyer is somewhere else: adding a car in chat and only learning it worked by
 * navigating to `/cart` would make the add feel like it went nowhere.
 *
 * Renders for a signed-in buyer only. A seller has no cart, and an anonymous visitor has
 * nowhere to put one yet -- P12 deliberately leaves `/` unguarded, so "no badge" is the
 * honest state rather than a prompt to sign in before the agent has said a word.
 */
import { Link } from "react-router-dom";
import { useSession } from "../auth/SessionContext";
import { useCart } from "./CartContext";

export function CartBadge(): React.ReactElement | null {
  const { status, session } = useSession();
  const { count } = useCart();

  if (status !== "authenticated" || session?.account.role !== "buyer") return null;

  return (
    <Link
      to="/cart"
      className="cart-badge"
      data-testid="cart-badge"
      aria-label={`Cart, ${count} ${count === 1 ? "car" : "cars"}`}
    >
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
        <path
          d="M3 4h2.2l2.1 10.1a2 2 0 002 1.6h7.8a2 2 0 002-1.6L20.5 7H7"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="10" cy="19.5" r="1.4" fill="currentColor" />
        <circle cx="17" cy="19.5" r="1.4" fill="currentColor" />
      </svg>
      <span className="cart-badge-count" data-testid="cart-badge-count">
        {count}
      </span>
    </Link>
  );
}
