/**
 * The one navigation bar every route shares.
 *
 * Three zones, which is how Cohere's global nav is built and also how the configurator layout
 * in the design brief is built: brand left, menu centred in a pill group, account and cart
 * right. The centred pill group is the part that carries the look — an active route is a filled
 * near-black pill, everything else is quiet text.
 *
 * Two rules govern what appears, unchanged from the first version:
 *
 * 1. **Links follow the role, not the routes.** A buyer never sees a seller link they would be
 *    bounced off (`RequireRole` redirects them straight back), and a seller never sees a cart
 *    they cannot have. Offering a control that is going to refuse you is worse than not
 *    offering it.
 * 2. **The header never blocks the agent.** `/` is the public showroom, so the signed-out state
 *    shows "Sign in" beside a working front page rather than in place of it.
 *
 * The "Agent" link is deliberately shown to anonymous visitors even though `/chat` is guarded.
 * That is not a control that refuses you — it is the product's front door, and the sign-in it
 * routes through remembers where you were going.
 */
import { Link, useLocation } from "react-router-dom";
import { useSession } from "./auth/SessionContext";
import { CartBadge } from "./cart/CartBadge";

export function SiteHeader(): React.ReactElement {
  const { status, session, signOut } = useSession();
  const { pathname } = useLocation();
  const role = session?.account.role;

  // `end`-style matching: `/` would otherwise read as current on every route.
  const isCurrent = (path: string) => (path === "/" ? pathname === "/" : pathname.startsWith(path));

  return (
    <header className="site-header" data-testid="site-header">
      <Link to="/" className="site-brand" aria-label="Cardinal home">
        <span className="site-brand-mark" aria-hidden="true">
          C
        </span>
        <span className="site-brand-text">
          <span className="site-brand-name">Cardinal</span>
          <span className="site-brand-sub">Car matchmaker</span>
        </span>
      </Link>

      <nav className="site-nav" aria-label="Main">
        <Link to="/" data-testid="nav-browse" aria-current={isCurrent("/") ? "page" : undefined}>
          Showroom
        </Link>
        {role !== "seller" && (
          <Link
            to="/chat"
            data-testid="nav-chat"
            aria-current={isCurrent("/chat") ? "page" : undefined}
          >
            Agent
          </Link>
        )}
        {role === "buyer" && (
          <Link
            to="/cart"
            data-testid="nav-cart"
            aria-current={isCurrent("/cart") ? "page" : undefined}
          >
            Cart
          </Link>
        )}
        {role === "seller" && (
          <Link
            to="/seller"
            data-testid="nav-seller"
            aria-current={isCurrent("/seller") ? "page" : undefined}
          >
            Leads
          </Link>
        )}
      </nav>

      <div className="site-account">
        <CartBadge />
        {status === "authenticated" && session ? (
          <>
            <span className="site-account-name" data-testid="nav-account">
              {session.account.full_name}
            </span>
            <button
              type="button"
              className="site-signout"
              data-testid="nav-signout"
              onClick={() => void signOut()}
            >
              Sign out
            </button>
          </>
        ) : (
          // `status === "loading"` deliberately shows this too: the first paint happens before
          // `/auth/me` answers, and flashing a name that then disappears is worse than a
          // "Sign in" link that quietly becomes one.
          <Link to="/login" className="site-signin" data-testid="nav-signin">
            Sign in
          </Link>
        )}
      </div>
    </header>
  );
}
