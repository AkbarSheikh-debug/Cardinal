/**
 * The `/seller/*` client -- PLAN-02 P15.
 *
 * Every route lives one level below `/seller`, for the reason D-076 records for `/cart`:
 * `/seller` is also the page this app navigates to, and neither nginx nor Vite can tell a
 * navigation from a `fetch()` by path alone. There is no bare `/seller` endpoint and there
 * must never be one.
 *
 * Note what these types do **not** contain: no income, no band, no employer. That is not a
 * client-side omission to be careful about -- `src/api/leads.py` builds the seller-facing
 * payload field by field and those fields are not in it (gate 15.7). This file describing
 * them would be the first step toward one of them arriving.
 */

export type IntentTier = "high" | "medium" | "low";
export type LeadState = "new" | "viewed" | "contacted" | "closed";

export interface LeadSignal {
  name: string;
  value: number;
  weight: number;
  contribution: number;
  /** A sentence, not a number: "target date is 5 days away" is actionable, `0.28` is not. */
  explanation: string;
}

export interface LeadListing {
  headline: string;
  price: { amount: string; currency: string } | null;
  condition: string;
  /** False once the car has been withdrawn -- the card says so rather than going quiet. */
  available: boolean;
}

export interface Lead {
  id: string;
  state: LeadState;
  created_at: string;
  updated_at: string;
  source: string;
  source_id: string;
  /** Resolved fresh on every read, so the price a salesperson quotes is the current one.
   * `null` once the listing is gone from the catalogue entirely. */
  listing: LeadListing | null;
  requirement_summary: string;
  events: string[];
  buyer: { full_name: string | null; email: string | null; phone: string | null };
  tier: IntentTier;
  /** Always phrased as an estimate, server-side, so the wording lives in exactly one place. */
  tier_label: string;
  guidance: string;
  score: number;
  explanation: string;
  signals: LeadSignal[];
  sla_deadline: string | null;
  overdue: boolean;
}

export interface DealerOption {
  id: string;
  display_name: string;
  city: string;
  country: string;
  verified: boolean;
}

export interface Analytics {
  total: number;
  by_tier: Record<IntentTier, number>;
  open: number;
  overdue: number;
  by_day: Array<{ date: string } & Record<string, number | string>>;
}

export interface SellerBoard {
  dealer: DealerOption | null;
  seller: { full_name: string; email: string };
  leads: Lead[];
  analytics: Analytics;
}

export class SellerError extends Error {}

async function detailOf(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    return typeof body?.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

export async function fetchBoard(): Promise<SellerBoard> {
  const response = await fetch("/seller/leads", { credentials: "include" });
  if (!response.ok) throw new SellerError(await detailOf(response, "could not load your leads"));
  return response.json();
}

export async function markContacted(leadId: string): Promise<Lead> {
  const response = await fetch(`/seller/leads/${leadId}/contacted`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) throw new SellerError(await detailOf(response, "could not update that lead"));
  return response.json();
}

/** The dealership picker on the seller side of the login form. Unauthenticated by design --
 * everything in it is already on every result card a buyer sees. */
export async function fetchDealers(): Promise<DealerOption[]> {
  try {
    const response = await fetch("/seller/dealers");
    if (!response.ok) return [];
    const body: unknown = await response.json();
    return Array.isArray(body) ? (body as DealerOption[]) : [];
  } catch {
    return [];
  }
}
