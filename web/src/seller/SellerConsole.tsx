/**
 * The seller console -- PLAN-02 P15. The other half of the product.
 *
 * Three things on this screen are load-bearing rather than decorative:
 *
 * - **Every tier reads as an estimate with its reasoning attached** (gate 15.8). The label
 *   comes from the server (`IntentTier.label`) so the wording lives in one place, and the
 *   sentence under it names the signals that produced it. A dashboard that asserted "this
 *   person will buy" would be making a claim about someone's mind that nobody here can make.
 * - **"Why this tier" is the arithmetic, not a summary of it.** Every signal, its
 *   contribution, and its own sentence. The contributions sum to the score because there is
 *   no hidden term -- income is not an input at all (D-079).
 * - **Contact details are here because an intent action happened.** A lead cannot exist
 *   without one, so there is no branch to get wrong: browsing produces nothing to render.
 *
 * The live channel is `GET /seller/events`, which pushes a *nudge* rather than a lead. This
 * component refetches on one, which keeps `/seller/leads` the only code path that decides
 * what a seller may see.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchBoard,
  markContacted,
  type Lead,
  type LeadSignal,
  type SellerBoard,
} from "./api";

const TIER_CLASS: Record<string, string> = { high: "tier-high", medium: "tier-med", low: "tier-low" };

const SIGNAL_LABEL: Record<string, string> = {
  target_date_proximity: "When they need it",
  opened_checkout: "Opened checkout",
  added_to_cart: "Added to cart",
  booking_submitted: "Booking form submitted",
  budget_fit: "Fits their stated budget",
  return_sessions: "Return visits",
  corporate_customer: "Business buyer",
};

function countdown(deadline: string | null, overdue: boolean): string {
  if (!deadline) return "No deadline — follow your own cadence";
  const ms = new Date(deadline).getTime() - Date.now();
  if (overdue || ms <= 0) return "Overdue";
  const hours = Math.floor(ms / 3_600_000);
  const minutes = Math.floor((ms % 3_600_000) / 60_000);
  return hours > 0 ? `${hours}h ${minutes}m left` : `${minutes}m left`;
}

function SignalRow({ signal }: { signal: LeadSignal }) {
  // Every signal the scorer defines carries a non-negative weight, so in practice this is
  // always "+". Deriving the sign rather than hardcoding it costs nothing and means a signal
  // that ever *subtracts* renders as "-0.066" instead of "+-0.066"; `data-sign` lets the bar
  // turn coral for the same case without the stylesheet having to guess.
  const negative = signal.contribution < 0;
  return (
    <li className="signal-row" data-testid="lead-signal" data-sign={negative ? "negative" : "positive"}>
      <span className="signal-name">{SIGNAL_LABEL[signal.name] ?? signal.name}</span>
      <span className="signal-bar" aria-hidden="true">
        <span className="signal-fill" style={{ width: `${Math.round(signal.value * 100)}%` }} />
      </span>
      <span className="signal-why">{signal.explanation}</span>
      <span className="signal-contribution">
        {negative ? "-" : "+"}
        {Math.abs(signal.contribution).toFixed(3)}
      </span>
    </li>
  );
}

function LeadCard({ lead, onContacted }: { lead: Lead; onContacted: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const total = lead.signals.reduce((sum, s) => sum + s.contribution, 0);

  return (
    <article className="lead-card" data-testid="lead-card" data-tier={lead.tier}>
      <header className="lead-head">
        <div>
          {/* The estimate phrasing gate 15.8 asserts on rendered text. */}
          <p className={`lead-tier ${TIER_CLASS[lead.tier]}`} data-testid="lead-tier">
            {lead.tier_label}
          </p>
          <h3 data-testid="lead-buyer">{lead.buyer.full_name ?? "Unnamed buyer"}</h3>
        </div>
        <span
          className={`lead-sla ${lead.overdue ? "overdue" : ""}`}
          data-testid="lead-sla"
        >
          {countdown(lead.sla_deadline, lead.overdue)}
        </span>
      </header>

      {/* The reasoning, always next to the tier -- never a bare verdict. */}
      <p className="lead-explanation" data-testid="lead-explanation">
        {lead.explanation}
      </p>
      <p className="lead-guidance">{lead.guidance}</p>

      <dl className="lead-facts">
        <div>
          <dt>Car</dt>
          <dd data-testid="lead-listing">
            {/* The headline and the *current* price, resolved server-side on read. A
                salesperson cannot phone a buyer about "mock_autobazaar:AB-1001"; the
                reference stays visible underneath because it is what they'd search on. */}
            {lead.listing ? (
              <>
                {lead.listing.headline}
                {lead.listing.price && (
                  <span className="lead-listing-price">
                    {" "}
                    · {lead.listing.price.currency}{" "}
                    {Number(lead.listing.price.amount).toLocaleString("en-GB", {
                      maximumFractionDigits: 0,
                    })}
                  </span>
                )}
                {!lead.listing.available && (
                  <span className="lead-listing-gone"> · withdrawn from sale</span>
                )}
                <span className="lead-listing-ref">
                  {lead.source}:{lead.source_id}
                </span>
              </>
            ) : (
              `${lead.source}:${lead.source_id}`
            )}
          </dd>
        </div>
        <div>
          <dt>Looking for</dt>
          <dd data-testid="lead-summary">{lead.requirement_summary}</dd>
        </div>
        <div>
          <dt>Contact</dt>
          <dd data-testid="lead-contact">
            {lead.buyer.email}
            {lead.buyer.phone ? ` · ${lead.buyer.phone}` : ""}
          </dd>
        </div>
      </dl>

      <button
        type="button"
        className="lead-why-toggle"
        data-testid="lead-why-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Hide why this tier" : "Why this tier?"}
      </button>

      {open && (
        <div className="lead-why" data-testid="lead-why">
          <ul className="signal-list">
            {lead.signals.map((s) => (
              <SignalRow key={s.name} signal={s} />
            ))}
          </ul>
          {/* Stated, not implied: the rows above *are* the score. Nothing is withheld, which
              is only true because income was never an input (D-079). */}
          <p className="signal-total" data-testid="lead-signal-total">
            {lead.signals.length} signals, contributions total {total.toFixed(3)} — the whole
            score. Nothing else feeds this number.
          </p>
        </div>
      )}

      <footer className="lead-actions">
        <span className={`lead-state state-${lead.state}`} data-testid="lead-state">
          {lead.state}
        </span>
        {lead.state !== "contacted" && lead.state !== "closed" && (
          <button
            type="button"
            className="lead-contacted"
            data-testid="lead-mark-contacted"
            onClick={() => onContacted(lead.id)}
          >
            Mark contacted
          </button>
        )}
      </footer>
    </article>
  );
}

function AnalyticsStrip({ board }: { board: SellerBoard }) {
  const { analytics } = board;
  const peak = Math.max(
    1,
    ...analytics.by_day.map((d) => Number(d.high) + Number(d.medium) + Number(d.low)),
  );
  return (
    <section className="seller-analytics" data-testid="seller-analytics">
      <div className="analytics-counts">
        <span data-testid="analytics-total">
          <strong>{analytics.total}</strong> leads
        </span>
        <span className="tier-high">
          <strong>{analytics.by_tier.high}</strong> high
        </span>
        <span className="tier-med">
          <strong>{analytics.by_tier.medium}</strong> medium
        </span>
        <span className="tier-low">
          <strong>{analytics.by_tier.low}</strong> low
        </span>
        <span className={analytics.overdue > 0 ? "overdue" : ""}>
          <strong>{analytics.overdue}</strong> overdue
        </span>
      </div>
      <div className="analytics-days" aria-label="Leads per day, last 7 days">
        {analytics.by_day.map((day) => {
          const counts = [Number(day.high), Number(day.medium), Number(day.low)];
          const totalForDay = counts[0] + counts[1] + counts[2];
          return (
            <div key={String(day.date)} className="analytics-day" title={`${day.date}: ${totalForDay}`}>
              <div className="analytics-stack">
                {["high", "med", "low"].map((cls, i) => (
                  <span
                    key={cls}
                    className={`analytics-seg tier-${cls}`}
                    style={{ height: `${(counts[i] / peak) * 100}%` }}
                  />
                ))}
              </div>
              <span className="analytics-day-label">{String(day.date).slice(5)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function SellerConsole(): React.ReactElement {
  const [board, setBoard] = useState<SellerBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const boardRef = useRef<SellerBoard | null>(null);
  boardRef.current = board;

  const load = useCallback(async () => {
    try {
      setBoard(await fetchBoard());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not load your leads");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // PLAN-02 §0.4: the same SSE pattern the buyer session uses, a second consumer. The event
  // is a nudge, not a lead -- refetching keeps `/seller/leads` the only place that decides
  // what a seller may see, rather than a second serialiser that has to agree with it.
  useEffect(() => {
    const source = new EventSource("/seller/events", { withCredentials: true });
    source.onopen = () => setLive(true);
    source.onerror = () => setLive(false);
    source.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message?.kind === "ready") {
        setLive(true);
        return;
      }
      if (message?.kind === "lead") void load();
    };
    return () => source.close();
  }, [load]);

  const onContacted = useCallback(async (id: string) => {
    try {
      const updated = await markContacted(id);
      const current = boardRef.current;
      if (!current) return;
      setBoard({
        ...current,
        leads: current.leads.map((lead) => (lead.id === id ? updated : lead)),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not update that lead");
    }
  }, []);

  /**
   * The dealership once one is resolved, and the page's own name until then.
   *
   * Never the signed-in person's name: a page title should say what the page *is*. The
   * fallback also matters beyond taste — a seller whose account was never linked to a
   * dealership (D-080) lands here, and "Seller console" over an explanatory error is a far
   * better answer than their own name over an empty list.
   *
   * Gate 12.2 asserts the console *renders*, not this string: a linked seller sees their
   * dealership's name, so an assertion on "Seller console" would only pass for an account
   * that is broken -- which is exactly how it passed before the signup form made the
   * dealership `required`.
   */
  const heading = useMemo(() => board?.dealer?.display_name ?? "Seller console", [board]);

  return (
    <main className="seller-console" data-testid="seller-console">
      <header>
        <div>
          <h1 data-testid="seller-dealer">{heading}</h1>
          <p className="seller-sub">
            <span className={`dot ${live ? "dot-ok" : "dot-bad"}`} />
            {live ? "Live — new leads arrive here" : "Reconnecting"}
            {board?.dealer ? ` · ${board.dealer.city}, ${board.dealer.country}` : ""}
          </p>
        </div>
        {/* Sign-out moved to `SiteHeader` when the routes became one navigable site. Two
            buttons doing the same thing on one screen is the same duplication the cart badge
            had -- and the site-chrome one is on every route, not just this page. */}
      </header>

      {error && (
        <p className="login-error" role="alert" data-testid="seller-error">
          {error}
        </p>
      )}

      {board && <AnalyticsStrip board={board} />}

      {board && board.leads.length === 0 && (
        <p className="placeholder-note" data-testid="seller-empty">
          No leads yet. One appears the moment a buyer adds one of your cars to their cart,
          opens checkout, or submits a booking form — browsing alone never creates one, and
          never exposes anyone's contact details.
        </p>
      )}

      <div className="lead-list">
        {board?.leads.map((lead) => (
          <LeadCard key={lead.id} lead={lead} onContacted={(id) => void onContacted(id)} />
        ))}
      </div>
    </main>
  );
}
