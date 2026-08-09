/**
 * The `/cart` page body -- PLAN-02 P14.
 *
 * Renders in `App`'s canvas slot rather than as a route of its own, which is what makes
 * PLAN-02 §0.1 literally true instead of true by argument: the chat rail beside this panel is
 * the *same component instance* on the *same* agent session and the *same* SSE stream the
 * buyer was already talking on. There is no second session to keep in sync and no second
 * transport to configure, and the checkout App mounts through `App`'s existing `McpAppHost` --
 * the identical host, resource and audit path gates 7.x and 8.x already drive in chat.
 *
 * Nothing here mints a gesture token, calls `submit_booking_draft`, or carries a price into
 * checkout. "Proceed to checkout" opens the *booking form* App and stops; everything after
 * that is P7/P8's already-gated sequence (CONSTITUTION I.2, gate 14.6).
 */
import { useEffect, useState } from "react";
import { startCheckout, type CartLine, type Payee } from "./api";
import { useCart } from "./CartContext";

const CONDITION_LABEL: Record<string, string> = {
  new: "New",
  used: "Used",
  certified_pre_owned: "Certified pre-owned",
};

const OFFER_LABEL: Record<string, string> = {
  buy: "Purchase",
  rent: "Rental",
  both: "Purchase",
};

/**
 * Who receives the money, on the line itself -- before the buyer has even opened checkout.
 *
 * The checkout App renders this same disclosure again above its pay control (gate 14.4);
 * showing it here too is not duplication, it is the difference between finding out who you
 * are paying at the moment of paying and knowing before you decide to.
 *
 * An unknown payee renders as an explicit statement, never as an omitted block. Silence reads
 * as "there was nothing to say", which is precisely the wrong thing to say about this.
 */
function PayeeBlock({ payee }: { payee: Payee | null }) {
  if (!payee) {
    return (
      <div className="cart-payee" data-testid="cart-payee" data-flag="yes">
        <h4>Who you would be paying</h4>
        <p className="cart-payee-unknown" data-testid="cart-payee-status">
          PAYEE IDENTITY UNVERIFIED — we could not confirm who receives this payment.
        </p>
      </div>
    );
  }
  return (
    <div className="cart-payee" data-testid="cart-payee" data-flag={payee.needs_flag ? "yes" : "no"}>
      <h4>Who you would be paying</h4>
      <p className="cart-payee-legal" data-testid="cart-payee-legal-name">
        {payee.legal_name}
      </p>
      <p className="cart-payee-address" data-testid="cart-payee-address">
        {[payee.address, payee.city, payee.country].filter(Boolean).join(", ")}
      </p>
      <p className="cart-payee-phone" data-testid="cart-payee-phone">
        {payee.phone}
      </p>
      <p className="cart-payee-status" data-testid="cart-payee-status">
        {payee.needs_flag
          ? payee.verification_status === "pending"
            ? "PAYEE IDENTITY UNVERIFIED — this business is still being checked."
            : "PAYEE IDENTITY UNVERIFIED — this business has not been checked."
          : "Verified business — identity confirmed by the marketplace."}
      </p>
    </div>
  );
}

function priceOf(line: CartLine): string {
  if (!line.price) return "Price on request";
  const amount = Number(line.price.amount);
  const formatted = Number.isFinite(amount)
    ? amount.toLocaleString("en-GB", { maximumFractionDigits: 0 })
    : line.price.amount;
  return line.offer_type === "rent"
    ? `${line.price.currency} ${formatted} / day`
    : `${line.price.currency} ${formatted}`;
}

function CartLineCard({ line, sessionId }: { line: CartLine; sessionId: string }) {
  const { remove } = useCart();
  const [opening, setOpening] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const unavailable = !line.available;

  async function proceed(): Promise<void> {
    setFailure(null);
    setOpening(true);
    try {
      await startCheckout(sessionId, line.item_id);
    } catch (err) {
      setFailure(err instanceof Error ? err.message : "could not start checkout");
    } finally {
      // Always cleared, including on the failure path: a spinner that never resolves is the
      // worst possible way to tell somebody their car is gone (gate 14.10).
      setOpening(false);
    }
  }

  return (
    <article className="cart-line" data-testid="cart-line" data-available={line.available}>
      <div className="cart-line-head">
        <h3 data-testid="cart-line-headline">
          {line.headline ?? `${line.source}:${line.source_id}`}
        </h3>
        <span className="cart-line-price" data-testid="cart-line-price">
          {priceOf(line)}
        </span>
      </div>

      <p className="cart-line-meta">
        <span className="cart-line-offer">{OFFER_LABEL[line.offer_type] ?? line.offer_type}</span>
        {line.condition && (
          <span className="cart-line-condition">
            {CONDITION_LABEL[line.condition] ?? line.condition}
          </span>
        )}
      </p>

      <PayeeBlock payee={line.payee} />

      {(unavailable || failure) && (
        <p className="cart-line-unavailable" data-testid="cart-line-unavailable" role="alert">
          {unavailable
            ? "This car has been withdrawn from the marketplace. It cannot be checked out."
            : failure}
        </p>
      )}

      <div className="cart-line-actions">
        <button
          type="button"
          className="cart-line-checkout"
          data-testid="cart-line-checkout"
          disabled={unavailable || opening}
          onClick={() => void proceed()}
        >
          {opening ? "Opening…" : "Proceed to checkout"}
        </button>
        <button
          type="button"
          className="cart-line-remove"
          data-testid="cart-line-remove"
          onClick={() => void remove(line.item_id)}
        >
          Remove
        </button>
      </div>
    </article>
  );
}

export function CartPanel({ sessionId }: { sessionId: string }): React.ReactElement {
  const { cart, error, refresh } = useCart();

  // `CartProvider` sits above the router and does not remount on navigation, so arriving here
  // would otherwise show whatever the badge last knew. Prices and a dealer's verification
  // status are both re-resolved server-side on every read (`_payload`'s own note) -- this is
  // the page where being a few minutes stale about either actually costs something.
  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!cart) {
    return (
      <div className="cart-panel" data-testid="cart-panel">
        <h2>Your cart</h2>
        <p className="cart-empty">Sign in as a buyer to keep a shortlist.</p>
      </div>
    );
  }

  return (
    <div className="cart-panel" data-testid="cart-panel">
      <header className="cart-panel-head">
        <h2>Your cart</h2>
        <p className="cart-panel-count" data-testid="cart-panel-count">
          {cart.count} {cart.count === 1 ? "car" : "cars"}
        </p>
      </header>

      {error && (
        <p className="cart-error" role="alert">
          {error}
        </p>
      )}

      {cart.items.length === 0 ? (
        <p className="cart-empty" data-testid="cart-empty">
          Nothing here yet. Add a car from the shortlist Cardinal builds for you, then come
          back — the conversation carries on beside this page.
        </p>
      ) : (
        <>
          {cart.items.map((line) => (
            <CartLineCard key={line.item_id} line={line} sessionId={sessionId} />
          ))}
          {/* No cart-wide total, deliberately: `[MVP]` checkout runs on one line (PLAN-02
              P14), and a sum across a rental and a purchase is a number with no meaning. */}
          <p className="cart-single-note">
            Checkout runs one car at a time. Everything else stays here as your shortlist.
          </p>
        </>
      )}
    </div>
  );
}
