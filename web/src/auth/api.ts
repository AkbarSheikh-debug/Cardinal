/**
 * The `/auth/*` client -- PLAN-02 P12.
 *
 * Every call sends `credentials: "include"` so the httpOnly session cookie the backend sets
 * actually rides along. The token is deliberately *not* stored in `localStorage`: page
 * JavaScript can't read an httpOnly cookie, which is the whole point of setting one
 * (PLAN-02 §0.2). `verify-otp` does return the token in its body for non-browser clients
 * (gates, tests); this module ignores that field on purpose rather than stashing it.
 */

export type AccountRole = "buyer" | "seller";

export type CustomerType = "individual" | "corporate";

export interface Account {
  id: string;
  role: AccountRole;
  email: string;
  full_name: string;
  phone: string;
  created_at: string;
}

export interface BuyerProfile {
  account_id: string;
  customer_type: CustomerType;
  employer: string | null;
  annual_income: { amount: string; currency: string } | null;
  /** Derived server-side from `annual_income` -- never sent up, never trusted from here. */
  income_band: string;
  /** `null` means not stated: a Google sign-in carries no address, and the server records
   *  that rather than inventing one. The signup form still requires both. */
  city: string | null;
  country: string | null;
}

export interface SellerProfile {
  account_id: string;
  dealer_id: string | null;
  role_title: string;
}

export interface Session {
  account: Account;
  profile: BuyerProfile | SellerProfile | null;
}

export interface OtpChallenge {
  email: string;
  role: AccountRole;
  expires_at: string;
  banner: string;
  /** Honest mock: there is no channel to deliver a code on, so the API says so. */
  demo_codes: string[];
}

export class AuthError extends Error {}

async function post(path: string, body: unknown): Promise<Response> {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
}

async function detailOf(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    return typeof body?.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

export async function requestOtp(email: string, role: AccountRole): Promise<OtpChallenge> {
  const response = await post("/auth/request-otp", { email, role });
  if (!response.ok) {
    throw new AuthError(await detailOf(response, "could not start the login"));
  }
  return response.json();
}

export interface VerifyInput {
  email: string;
  role: AccountRole;
  code: string;
  fullName: string;
  phone: string;
  profile: Record<string, unknown>;
}

export async function verifyOtp(input: VerifyInput): Promise<{ account: Account; created: boolean }> {
  const response = await post("/auth/verify-otp", {
    email: input.email,
    role: input.role,
    code: input.code,
    full_name: input.fullName,
    phone: input.phone,
    profile: input.profile,
  });
  if (!response.ok) {
    throw new AuthError(await detailOf(response, "that code did not work"));
  }
  return response.json();
}

/** `null` rather than a throw for the ordinary "not signed in" case -- it isn't an error. */
export async function fetchSession(): Promise<Session | null> {
  const response = await fetch("/auth/me", { credentials: "include" });
  if (response.status === 401) return null;
  if (!response.ok) throw new AuthError("could not read the session");
  return response.json();
}

export async function logout(): Promise<void> {
  await post("/auth/logout", {});
}

export interface Providers {
  google: boolean;
  demo_otp: boolean;
}

/**
 * Which sign-in methods this deployment can offer. The Google button is rendered only when
 * the server says the credentials exist -- showing it on a build with no client id produces a
 * click that dead-ends at Google's own error page, which the user cannot attribute to anyone.
 */
export async function fetchProviders(): Promise<Providers> {
  try {
    const response = await fetch("/auth/providers", { credentials: "include" });
    if (!response.ok) return { google: false, demo_otp: true };
    return response.json();
  } catch {
    return { google: false, demo_otp: true };
  }
}

/** A full-page navigation, not fetch: OAuth is a browser redirect flow by design. */
export function startGoogle(role: AccountRole): void {
  window.location.assign(`/auth/google/start?role=${encodeURIComponent(role)}`);
}

export async function claimDealership(dealerId: string): Promise<void> {
  const response = await post("/auth/claim-dealership", { dealer_id: dealerId });
  if (!response.ok) {
    throw new AuthError(await detailOf(response, "could not claim that dealership"));
  }
}

/**
 * A seller who has an account but no dealership yet.
 *
 * This state is reachable only through Google: the OTP form makes the picker `required`, but
 * Google's `email`/`profile` scopes carry no dealership and never could, so the question has
 * to be asked *after* the round trip instead of during it. Left unanswered it produces the
 * stuck console D-080 warns about -- signed in, no leads, and signing in again cannot fix it
 * because the account already exists.
 *
 * A missing profile counts: it means the same thing to the seller (an unfillable console) and
 * the claim endpoint repairs it identically.
 */
export function needsDealership(session: Session | null): boolean {
  if (!session || session.account.role !== "seller") return false;
  const { profile } = session;
  return profile === null || !("dealer_id" in profile) || !profile.dealer_id;
}
