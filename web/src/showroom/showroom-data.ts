/**
 * The showroom's content, in one place.
 *
 * **What this page now is.** The Paddock Green handoff replaced the configurator treatment —
 * facet rail, hotspot markers on the car, paint swatches — with a full-bleed photographic hero
 * that sells one car as a listing: price, monthly, mileage, seller. `PAINTS`, `FACETS` and the
 * `Hotspot` type went with the UI that read them, rather than being left behind as data nothing
 * renders.
 *
 * **On the numbers.** The four spec-rail figures are BMW's published numbers for the car in the
 * photograph (an M3 Competition xDrive, G80). The *listing* figures — asking price, monthly,
 * mileage, seller — are illustrative, because a showcase has no row in the catalogue to read
 * them from. The page says exactly that behind the ⓘ control next to the headline rather than
 * letting a visitor assume otherwise; this product's whole pitch is recommendations it can
 * defend, and a front page quoting a price it cannot source would undercut that on the first
 * screen anyone sees.
 *
 * The one live number on the page still comes from `/health` (see `ShowroomPage`) — a real
 * count of real seeded listings.
 */

export const VEHICLE = {
  eyebrow: "Showcase · 001",
  /** Two lines, set as two elements so the break is deliberate rather than a width accident. */
  headline: ["The M3", "Competition"] as const,
  blurb:
    "Isle of Man Green over Kyalami Orange, xDrive, and a paddock's worth of rain on the bonnet. One owner, full BMW history, ready to move today.",
  asking: { label: "Asking", value: "£79,450" },
  monthly: { label: "Monthly", value: "£1,240 / 48" },
  /** Manufacturer figures for the car in the frame — see the note above. */
  specs: ["510 hp", "3.5 s to 100", "M xDrive", "18,900 km"],
  seller: { name: "Munich Motors", verified: true },
  photoCredit: { source: "the project's own photography", note: "wet paddock, dusk" },
} as const;

/** The three-card "how this works" row. Wording tracks what the agent actually does. */
export const CAPABILITIES: { id: string; title: string; body: string }[] = [
  {
    id: "interview",
    title: "It interviews you first",
    body: "A handful of questions about budget, use and timing — then it tells you what it inferred, so you can correct it before it spends a single search.",
  },
  {
    id: "research",
    title: "It researches in parallel",
    body: "Rental and dealership marketplaces at once, with total cost of ownership modelled over your actual holding period rather than the sticker price.",
  },
  {
    id: "defend",
    title: "It defends the ranking",
    body: "Every recommendation opens into the weights that produced it. If you disagree with the reasoning, you can see exactly which number to argue with.",
  },
];
