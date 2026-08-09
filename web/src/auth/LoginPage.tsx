/**
 * `/login` -- PLAN-02 P12. Two-step: pick a role and enter an address, then enter a code and
 * the details the account needs. Google sign-in sits above that as a one-click alternative,
 * and adds a *third* screen that only it can reach -- see `claiming` below.
 *
 * The demo-auth banner is the first element inside `<main>` and is never conditional
 * (CONSTITUTION I.5 applied to auth exactly as it applies to payment). Gate 12.2 asserts it
 * from a real browser, above the fold, so its position here is load-bearing rather than
 * decorative -- do not move it below the form. It stays honest with Google in the mix: the
 * *identity* is really verified by Google, but the session Cardinal issues around it is still
 * the demo one, so the warning is if anything more necessary, not less.
 */
import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { fetchDealers, type DealerOption } from "../seller/api";
import {
  claimDealership,
  fetchProviders,
  needsDealership,
  requestOtp,
  startGoogle,
  verifyOtp,
  type AccountRole,
  type OtpChallenge,
  type Providers,
} from "./api";
import { destinationAfterSignIn } from "./destination";
import { useSession } from "./SessionContext";

const INCOME_HELP =
  "Optional. Used only to tailor affordability guidance — it is never shared with a dealer.";

/** Google's mark, inline. A remote image would be one more thing that can fail to load, and
 *  the button must not appear as a bare unbranded rectangle when it does. */
function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.41 5.41 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"
      />
    </svg>
  );
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { refresh, session } = useSession();
  const [searchParams] = useSearchParams();

  const [role, setRole] = useState<AccountRole>("buyer");
  const [email, setEmail] = useState("");
  const [challenge, setChallenge] = useState<OtpChallenge | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [code, setCode] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("DE");
  const [customerType, setCustomerType] = useState("individual");
  const [employer, setEmployer] = useState("");
  const [annualIncome, setAnnualIncome] = useState("");
  const [roleTitle, setRoleTitle] = useState("Sales");
  const [dealerId, setDealerId] = useState("");
  const [dealers, setDealers] = useState<DealerOption[]>([]);
  const [providers, setProviders] = useState<Providers>({ google: false, demo_otp: true });

  /**
   * The one screen only Google can reach: signed in as a seller, no dealership yet.
   *
   * Both halves matter. `LoginRoute` lets exactly this combination stay on `/login` and
   * redirects everything else away, so a stale `?claim=dealership` link on an account that
   * already has a dealership never renders a picker that would be refused.
   */
  const claiming = searchParams.get("claim") === "dealership" && needsDealership(session);

  // Fetched only once a dealership is actually going to be asked for -- a buyer signing in
  // should not pay for a list of 108 dealerships they will never see.
  useEffect(() => {
    if ((role === "seller" || claiming) && dealers.length === 0) {
      void fetchDealers().then(setDealers);
    }
  }, [role, claiming, dealers.length]);

  // Asked once per mount rather than per render: whether this deployment has Google
  // credentials cannot change while the page is open.
  useEffect(() => {
    void fetchProviders().then(setProviders);
  }, []);

  async function onRequest(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      setChallenge(await requestOtp(email, role));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "could not start the login");
    } finally {
      setBusy(false);
    }
  }

  async function onVerify(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // `income_band` is never sent: the server derives it (PLAN-02 §0.3), and a client that
      // offered one would simply have it ignored.
      const profile =
        role === "seller"
          ? { role_title: roleTitle, dealer_id: dealerId || null }
          : {
              city,
              country: country.toUpperCase(),
              customer_type: customerType,
              employer: employer.trim() || null,
              annual_income: annualIncome.trim()
                ? { amount: annualIncome.trim(), currency: "EUR" }
                : null,
            };
      await verifyOtp({ email, role, code, fullName, phone, profile });
      await refresh();
      navigate(destinationAfterSignIn(role, location), { replace: true });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "that code did not work");
    } finally {
      setBusy(false);
    }
  }

  async function onClaim(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await claimDealership(dealerId);
      // Refresh before navigating: `/seller` reads `dealer_id` off the session, and routing
      // there with the pre-claim copy still cached shows the empty console for one paint.
      await refresh();
      navigate("/seller", { replace: true });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "could not link that dealership");
    } finally {
      setBusy(false);
    }
  }

  if (claiming) {
    return (
      <main className="login">
        <h1>One more thing</h1>
        <p className="login-lede" data-testid="claim-step">
          Signed in as <strong>{session?.account.email}</strong>. Google can tell us who you
          are, but not who you work for — so this is the one question it cannot answer for you.
        </p>

        <form onSubmit={onClaim} className="login-form">
          <label>
            Your dealership
            <select
              required
              value={dealerId}
              onChange={(e) => setDealerId(e.target.value)}
              data-testid="dealer-picker"
            >
              <option value="">Select a dealership…</option>
              {dealers.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.display_name} — {d.city}
                  {d.verified ? " ✓" : ""}
                </option>
              ))}
            </select>
            <small>
              Leads for this dealership's cars arrive on your console. Demo auth does not
              verify the claim — real provisioning is a production concern.
            </small>
          </label>
          <button type="submit" disabled={busy} data-testid="claim-submit">
            {busy ? "Linking…" : "Continue"}
          </button>
        </form>

        {error && (
          <p className="login-error" role="alert" data-testid="login-error">
            {error}
          </p>
        )}
      </main>
    );
  }

  return (
    <main className="login">
      <div className="login-col">
        <h1>Sign in to Cardinal</h1>

      <div className="role-toggle" role="group" aria-label="Account type">
        <button
          type="button"
          aria-pressed={role === "buyer"}
          className={role === "buyer" ? "active" : ""}
          onClick={() => setRole("buyer")}
          disabled={challenge !== null}
        >
          I'm buying or renting
        </button>
        <button
          type="button"
          aria-pressed={role === "seller"}
          className={role === "seller" ? "active" : ""}
          onClick={() => setRole("seller")}
          disabled={challenge !== null}
        >
          I'm selling
        </button>
      </div>

      {/* Rendered only when the server says the credentials exist. A "Continue with Google"
          button on a build with no client id produces a click that dead-ends on Google's own
          error page, which the user has no way to attribute to us. Hidden once a code has
          been requested: switching to Google mid-OTP would abandon a challenge already sent. */}
      {providers.google && challenge === null && (
        <>
          <button
            type="button"
            className="google-button"
            data-testid="google-signin"
            onClick={() => startGoogle(role)}
            disabled={busy}
          >
            <GoogleMark />
            Continue with Google
          </button>
          {/* The role toggle above decides which side of the product this lands on. Google
              cannot know whether someone is buying or selling, so the answer has to be picked
              before the redirect and carried across in the state cookie. */}
          <p className="auth-divider" role="separator">
            <span>or</span>
          </p>
        </>
      )}

      {challenge === null ? (
        <form onSubmit={onRequest} className="login-form">
          <label>
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? "Sending…" : "Send code"}
          </button>
        </form>
      ) : (
        <form onSubmit={onVerify} className="login-form">
          <label>
            Code
            <input
              required
              inputMode="numeric"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
              autoComplete="one-time-code"
            />
          </label>
          <label>
            Full name
            <input required value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </label>
          <label>
            Phone
            <input
              required
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+49 170 1234567"
              autoComplete="tel"
            />
          </label>

          {role === "buyer" ? (
            <>
              <label>
                City
                <input required value={city} onChange={(e) => setCity(e.target.value)} />
              </label>
              <label>
                Country
                <input
                  required
                  maxLength={2}
                  value={country}
                  onChange={(e) => setCountry(e.target.value)}
                />
              </label>
              <label>
                I'm buying as
                <select value={customerType} onChange={(e) => setCustomerType(e.target.value)}>
                  <option value="individual">An individual</option>
                  <option value="corporate">A business / fleet</option>
                </select>
              </label>
              <label>
                Employer <span className="optional">optional</span>
                <input value={employer} onChange={(e) => setEmployer(e.target.value)} />
              </label>
              <label>
                Annual income (EUR) <span className="optional">optional</span>
                <input
                  inputMode="numeric"
                  value={annualIncome}
                  onChange={(e) => setAnnualIncome(e.target.value)}
                  placeholder="Prefer not to say"
                />
                <small>{INCOME_HELP}</small>
              </label>
            </>
          ) : (
            <>
              <label>
                Your role
                <input value={roleTitle} onChange={(e) => setRoleTitle(e.target.value)} />
              </label>
              {/* PLAN-02 P15. Which dealership this account represents, and the thing every
                  lead is routed by. Chosen rather than derived: with demo auth there is no
                  provisioning step to inherit it from, and a seller who lands on an empty
                  console because nobody linked their account is the single most confusing
                  way this feature can fail (`src/api/auth.py`'s `_validate_dealer_claim`). */}
              <label>
                Your dealership
                {/* `required`, because the profile is written once at signup: a seller who
                    submits without choosing lands on a console that can never fill, and no
                    amount of signing in again fixes it (the account already exists, so
                    `verify_otp` reuses it and ignores the profile). Refusing the empty
                    submission is the only place that state can actually be prevented. */}
                <select
                  required
                  value={dealerId}
                  onChange={(e) => setDealerId(e.target.value)}
                  data-testid="dealer-picker"
                >
                  <option value="">Select a dealership…</option>
                  {dealers.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.display_name} — {d.city}
                      {d.verified ? " ✓" : ""}
                    </option>
                  ))}
                </select>
                <small>
                  Leads for this dealership's cars arrive on your console. Demo auth does not
                  verify the claim — real provisioning is a production concern.
                </small>
              </label>
            </>
          )}

          <button type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <button type="button" className="link" onClick={() => setChallenge(null)}>
            Use a different email
          </button>
        </form>
      )}

      {error && (
        <p className="login-error" role="alert" data-testid="login-error">
          {error}
        </p>
      )}
      </div>

      {/* Decorative: the form is the whole of the content, and this column repeats none of
          it. Hidden from assistive tech rather than given invented alt text. */}
      <aside className="login-aside" aria-hidden="true">
        <picture>
          <source type="image/webp" srcSet="/showroom/login-m5-620.webp 620w, /showroom/login-m5-1240.webp 1240w" sizes="620px" />
          <img src="/showroom/login-m5-620.jpg" srcSet="/showroom/login-m5-620.jpg 620w, /showroom/login-m5-1240.jpg 1240w" sizes="620px" alt="" loading="lazy" decoding="async" />
        </picture>
        <div className="login-aside-caption">
          <p className="login-aside-eyebrow">Why sign in</p>
          <p>The agent remembers your budget, your horizon and what you already rejected.</p>
        </div>
      </aside>
    </main>
  );
}
