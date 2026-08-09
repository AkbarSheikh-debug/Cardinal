/**
 * The route table -- PLAN-02 P12 §2.1, revised when the site gained a front page.
 *
 * `App` (the chat rail + A2UI canvas + MCP App host, PHASE-6/7) is unchanged. What changed is
 * its address: it now lives at `/chat`, and `/` is the public showroom.
 *
 * **Why the move.** D-085 settled that a buyer signs in before the agent says a word, and that
 * still holds -- `/chat` is guarded exactly as `/` was. What D-085 did not settle is what a
 * stranger should see *first*, and the answer was "a login form", which is a poor answer for a
 * product whose pitch has to land before anyone will type an email address. The showroom is
 * that answer: open to everyone, no session, no agent call, and every route into the product
 * runs through the same guard it always did.
 *
 * So the guard did not weaken. It moved one hop out, from the door of the building to the door
 * of the room where something is actually spent.
 *
 * `/seller` is P15's console: leads for this seller's dealership, scored and explained.
 *
 * `/cart` is P14's: identity is required at checkout, and this is checkout. `App` in `cart`
 * mode is the *same* component `/chat` renders -- same session, same SSE stream, same agent
 * still answering beside the order (PLAN-02 §0.1), with the cart panel where the A2UI canvas
 * sits.
 */
import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { SiteHeader } from "./SiteHeader";
import App from "./App";
import { LoginPage } from "./auth/LoginPage";
import { useSession } from "./auth/SessionContext";
import { needsDealership } from "./auth/api";
import { destinationAfterSignIn, homeFor } from "./auth/destination";
import type { AccountRole } from "./auth/api";
import { SellerConsole } from "./seller/SellerConsole";
import { ShowroomPage } from "./showroom/ShowroomPage";

function Loading() {
  return (
    <main className="route-loading" aria-busy="true">
      <p>Loading…</p>
    </main>
  );
}

/**
 * Redirects to `/login`, remembering where the user was headed so signing in returns them
 * there instead of dumping them on the home route.
 */
function RequireRole({ role, children }: { role?: AccountRole; children: ReactNode }) {
  const { status, session } = useSession();
  const location = useLocation();

  if (status === "loading") return <Loading />;
  if (status === "anonymous" || !session) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (role && session.account.role !== role) {
    // Send someone to their own side of the product rather than showing a bare "denied":
    // a seller landing on the buyer chat is a wrong turn, not an attack.
    return <Navigate to={homeFor(session.account.role)} replace />;
  }
  return <>{children}</>;
}

/** Sends an already-signed-in visitor to their own side instead of showing the form again. */
function LoginRoute() {
  const { status, session } = useSession();
  const location = useLocation();

  if (status === "loading") return <Loading />;
  if (status === "authenticated" && session) {
    // One deliberate exception to "signed in means you do not belong on /login": a seller who
    // arrived through Google is sent back here with `?claim=dealership` *because* they are
    // signed in, and bouncing them home would drop them on exactly the console that can never
    // fill -- the state the redirect exists to prevent. Both halves are checked, so a stale
    // link on an account that already has a dealership still redirects normally.
    const claiming = new URLSearchParams(location.search).get("claim") === "dealership";
    if (!(claiming && needsDealership(session))) {
      // The *same* destination `LoginPage` computes -- see `auth/destination.ts` on why
      // both compute it rather than one of them winning a race.
      return <Navigate to={destinationAfterSignIn(session.account.role, location)} replace />;
    }
  }
  return <LoginPage />;
}

/**
 * Every route inside one shared chrome, so the pages are a site rather than several apps that
 * happen to share a bundle. The header is outside `<Routes>` on purpose: it must not remount on
 * navigation, or the cart count would refetch and flicker on every page change.
 */
function SiteLayout({ children }: { children: ReactNode }) {
  return (
    <div className="site-shell">
      <SiteHeader />
      {children}
    </div>
  );
}

export function AppRoutes() {
  return (
    <SiteLayout>
      <Routes>
        {/* The front page. Public, on purpose -- see the note at the top of this file. */}
        <Route path="/" element={<ShowroomPage />} />

        <Route path="/login" element={<LoginRoute />} />

        <Route
          path="/seller"
          element={
            <RequireRole role="seller">
              <SellerConsole />
            </RequireRole>
          }
        />

        {/* The agent. Guarded (D-085); `RequireRole` remembers where you were headed, so signing
            in returns you here rather than dumping you on a route you did not ask for. */}
        <Route
          path="/chat"
          element={
            <RequireRole role="buyer">
              <App />
            </RequireRole>
          }
        />

        {/* PLAN-02 P14. Guarded, and this is the route D-085 meant: identity is required at
            checkout, and this is checkout. */}
        <Route
          path="/cart"
          element={
            <RequireRole role="buyer">
              <App mode="cart" />
            </RequireRole>
          }
        />

        {/* Unknown paths land on the showroom -- a stray URL ends on the product's front page
            rather than at a dead end or, worse, at a login form it cannot explain. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </SiteLayout>
  );
}
