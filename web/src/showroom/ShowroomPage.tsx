/**
 * The front page — Paddock Green.
 *
 * The composition is the handoff's `#3b`: a full-bleed photographic stage, darkened by a
 * left-to-right gradient so type reads on the left third while the car stays legible on the
 * right two-thirds; a text column of eyebrow → two-line display headline → blurb → price pair →
 * two CTAs; and a hairline detail rail across the bottom of the image carrying four spec labels
 * and a verified-seller chip.
 *
 * What went, and why it is not coming back quietly: the facet rail, the hotspot markers on the
 * car and the paint swatches are gone. They belonged to a configurator treatment of a studio
 * cutout; this hero sells a whole car in an environment, and pinning labelled dots onto a
 * rain-covered bonnet at dusk would be illegible as well as off-message.
 *
 * Two things this page still refuses to do, unchanged from the previous treatment and for the
 * same reason — it is the first screen a stranger sees, and the product's entire claim is that
 * it can defend what it tells you:
 *
 * - **No fake liveness.** The one live number is the catalogue count from `/health`; when the
 *   API is not up the strip shows the seeded figure rather than a spinner that never resolves.
 * - **No unsourced claim presented as fact.** The spec rail is BMW's own published figures; the
 *   listing figures are illustrative, and the ⓘ control beside the headline says so in words.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Separator } from "../ui";
import { CAPABILITIES, VEHICLE } from "./showroom-data";
import "./showroom.css";

/** Live catalogue size, or `null` while unknown / if the API is not reachable. */
function useCatalogueCount(): { listings: number; sources: number } | null {
  const [stats, setStats] = useState<{ listings: number; sources: number } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/health", { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error("unhealthy"))))
      .then((body: { listings?: number; sources?: Record<string, number> }) => {
        if (typeof body.listings === "number") {
          setStats({ listings: body.listings, sources: Object.keys(body.sources ?? {}).length });
        }
      })
      // Deliberately silent. A marketing page that shows the visitor a failed health check has
      // confused its own diagnostics for content; the static copy below is the fallback.
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  return stats;
}

function CapabilityIcon({ id }: { id: string }) {
  // Thin-line geometric marks. 1px strokes on `currentColor` so they inherit the surrounding
  // ink rather than carrying their own palette.
  const common = {
    width: 32,
    height: 32,
    viewBox: "0 0 32 32",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1,
    "aria-hidden": true as const,
  };
  if (id === "interview") {
    return (
      <svg {...common}>
        <circle cx="16" cy="16" r="12.5" />
        <path d="M8 13h16M8 19h10" />
      </svg>
    );
  }
  if (id === "research") {
    return (
      <svg {...common}>
        <path d="M3 16h9M20 16h9" />
        <circle cx="16" cy="16" r="4" />
        <circle cx="16" cy="6" r="2.5" />
        <circle cx="16" cy="26" r="2.5" />
        <path d="M16 8.5v3.5M16 20v3.5" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M4 26V13M12 26V7M20 26v-9M28 26V4" />
      <path d="M3 29h26" />
    </svg>
  );
}

export function ShowroomPage(): React.ReactElement {
  const [provenanceOpen, setProvenanceOpen] = useState(false);
  const stats = useCatalogueCount();

  return (
    <main className="showroom" data-testid="showroom">
      <section className="showroom-stage" aria-labelledby="showroom-heading">
        {/* The photograph is an <img> rather than a background-image so it can carry alt text
            and take part in responsive selection; the gradient sits over it as its own layer. */}
        <picture className="showroom-photo">
          <source
            type="image/webp"
            srcSet="/showroom/hero-paddock-1280.webp 1280w, /showroom/hero-paddock-1920.webp 1920w, /showroom/hero-paddock-3840.webp 3840w"
            sizes="100vw"
          />
          <img
            src="/showroom/hero-paddock-1920.jpg"
            srcSet="/showroom/hero-paddock-1280.jpg 1280w, /showroom/hero-paddock-1920.jpg 1920w, /showroom/hero-paddock-3840.jpg 3840w"
            sizes="100vw"
            width={3840}
            height={1600}
            alt="A rain-covered BMW M3 Competition in Isle of Man Green, parked in a paddock at dusk"
            /* The LCP element: eager, high priority, never lazy. */
            fetchPriority="high"
            decoding="async"
          />
        </picture>
        <div className="showroom-scrim" aria-hidden="true" />

        <div className="showroom-stage-inner">
          <div className="showroom-lede">
            <p className="showroom-eyebrow">
              {VEHICLE.eyebrow}
              <button
                type="button"
                className="showroom-info"
                aria-expanded={provenanceOpen}
                aria-label="About this showcase"
                onClick={() => setProvenanceOpen((open) => !open)}
              >
                i
              </button>
            </p>

            <h1 id="showroom-heading" className="showroom-display">
              {VEHICLE.headline.map((line) => (
                <span key={line}>{line}</span>
              ))}
            </h1>

            {provenanceOpen && (
              <div className="showroom-provenance" role="note">
                <p>
                  A showcase, not a live listing. The performance figures below are BMW's own
                  published numbers for this car; the asking price, monthly and mileage are
                  illustrative, because a showcase has no catalogue row to read them from.
                  Cardinal's actual inventory lives behind the agent.
                </p>
              </div>
            )}

            <p className="showroom-blurb">{VEHICLE.blurb}</p>

            <div className="showroom-price">
              <div>
                <p className="showroom-price-label">{VEHICLE.asking.label}</p>
                <p className="showroom-price-value">{VEHICLE.asking.value}</p>
              </div>
              <div>
                <p className="showroom-price-label">{VEHICLE.monthly.label}</p>
                <p className="showroom-price-monthly">{VEHICLE.monthly.value}</p>
              </div>
            </div>

            <div className="showroom-cta">
              <Button asChild size="lg">
                <Link to="/chat">Find mine with Cardinal</Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link to="/chat">Message the seller</Link>
              </Button>
            </div>
          </div>

          <div className="showroom-rail">
            <ul className="showroom-specs">
              {VEHICLE.specs.map((spec) => (
                <li key={spec}>{spec}</li>
              ))}
            </ul>
            <p className="showroom-seller">
              <span className="showroom-seller-mark" aria-hidden="true">
                ✓
              </span>
              {VEHICLE.seller.name} — {VEHICLE.seller.verified ? "verified seller" : "unverified"}
            </p>
          </div>
        </div>
      </section>

      {/* ---- what the product actually does ---- */}
      <section className="showroom-capabilities" id="how-it-works" aria-labelledby="how-heading">
        <div className="showroom-section-head">
          <Badge variant="mono">How it works</Badge>
          <h2 id="how-heading">A car search that can show its working</h2>
        </div>
        <ul className="showroom-capability-grid">
          {CAPABILITIES.map((capability) => (
            <li key={capability.id}>
              <div className="showroom-capability">
                <CapabilityIcon id={capability.id} />
                <h3>{capability.title}</h3>
                <p>{capability.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {/* ---- the trust claim ---- */}
      <section className="showroom-band" aria-labelledby="band-heading">
        <div className="showroom-band-inner">
          <Badge variant="mono" className="showroom-band-eyebrow">
            The rule that does not bend
          </Badge>
          <h2 id="band-heading">No booking is confirmed without your click.</h2>
          <p>
            The model can search, compare, price and prepare an order. It cannot confirm one — the
            confirming tool is not in the set the model can see, and the gesture that unlocks it has
            to come from your hand. That is enforced in the code, not in the prompt.
          </p>

          <Separator className="showroom-band-rule" />

          <dl className="showroom-stats">
            <div>
              <dt>Listings in the catalogue</dt>
              <dd>{stats ? stats.listings.toLocaleString("en-GB") : "240"}</dd>
            </div>
            <div>
              <dt>Marketplaces searched at once</dt>
              <dd>{stats?.sources ? stats.sources : 2}</dd>
            </div>
            <div>
              <dt>Confirmations without a human click</dt>
              <dd>0</dd>
            </div>
          </dl>
          {!stats && (
            <p className="showroom-stats-note">
              Catalogue figures shown from the seed; start the API to read them live.
            </p>
          )}
        </div>
      </section>

      <footer className="showroom-footer">
        <div className="showroom-footer-inner">
          <div>
            <p className="showroom-footer-mark">Cardinal</p>
            <p className="showroom-footer-tag">
              A multistep agent that interviews, researches and recommends — then books and pays
              inside the conversation.
            </p>
          </div>
          <nav className="showroom-footer-nav" aria-label="Footer">
            <Link to="/chat">Talk to the agent</Link>
            <Link to="/cart">Your cart</Link>
            <Link to="/login">Sign in</Link>
          </nav>
        </div>
        <Separator />
        <div className="showroom-footer-fine">
          <p>Built for the Amulate Summer Hackathon 2026.</p>
          <p>Vehicle photography: {VEHICLE.photoCredit.source}.</p>
        </div>
      </footer>
    </main>
  );
}

export default ShowroomPage;
