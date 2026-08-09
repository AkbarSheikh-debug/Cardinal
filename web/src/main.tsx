import "@google/model-viewer"; // side-effect: registers the <model-viewer> custom element
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { SessionProvider } from "./auth/SessionContext";
import { CartProvider } from "./cart/CartContext";
// Order is load-bearing, and these three sit **above** the route import on purpose. Vite emits
// CSS in module-graph order, so importing `routes` first would pull `showroom.css` in ahead of
// the kit and let `ui.css` override the page that composes it — which is exactly backwards, and
// showed up as card padding that silently ignored its own override.
//
// Layering, outermost first: tokens define the variables, the kit consumes them, `styles.css`
// (which predates both) reads the legacy aliases the token layer publishes, and page
// stylesheets pulled in by the router land last so they can override any of it.
import "./ui/tokens.css";
import "./ui/ui.css";
import "./styles.css";
import { AppRoutes } from "./routes";

const container = document.getElementById("root");
if (!container) {
  throw new Error("#root element not found");
}

// PLAN-02 P12 §2.1: the router wraps the existing app rather than replacing it. `App` still
// owns `/` and is unchanged; `SessionProvider` sits above the router so a route guard and
// the buyer header read one shared session rather than each fetching `/auth/me`.
//
// P14's `CartProvider` sits *inside* `SessionProvider` (it needs to know who is signed in
// before it asks for a cart) and *above* the router, for the same reason: the header badge on
// `/` and the panel on `/cart` read one shared count. Two independent fetches would let them
// disagree, which is the one thing a cart must never do.
createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <SessionProvider>
        <CartProvider>
          <AppRoutes />
        </CartProvider>
      </SessionProvider>
    </BrowserRouter>
  </StrictMode>,
);
