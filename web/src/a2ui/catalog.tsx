/**
 * `carCatalog`'s nine custom components (PHASE-6 SS3's table), registered against the real
 * `@a2ui/react/v0_9` API via the one adapter module (`./adapter.ts`). Deliberately plain
 * markup, not a design system -- the point this phase proves is that the *agent* composed
 * these surfaces through a validated wire protocol, not that they are polished.
 *
 * Every schema here is the client-side twin of `src/mcp/ui/catalog.py`'s `ComponentSpec`
 * table: same prop names, same required/optional split. If the two drift, `compose_surface`
 * accepts server-side what the renderer then can't draw -- which is exactly the failure
 * A2UI's client-enforced catalog model exists to prevent.
 */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { z } from "zod";
import { createComponentImplementation, type ReactComponentImplementation } from "./adapter";

const SlotSchema = z.object({
  name: z.string(),
  status: z.enum(["open", "filled"]),
});

const InterviewProgressApi = {
  name: "InterviewProgress",
  schema: z.object({
    slots: z.array(SlotSchema),
    phase: z.string(),
    reasoningTrace: z.array(z.string()).optional(),
  }),
};

const InterviewProgress = createComponentImplementation(InterviewProgressApi, ({ props }) => (
  <div className="cardinal-interview-progress" data-phase={props.phase}>
    <p className="cardinal-phase-label">Phase: {props.phase}</p>
    <ul>
      {props.slots.map((slot) => (
        <li key={slot.name} data-status={slot.status}>
          {slot.status === "filled" ? "✓" : "…"} {slot.name}
        </li>
      ))}
    </ul>
    {props.reasoningTrace && (
      <ul className="cardinal-reasoning-trace">
        {props.reasoningTrace.map((line: string, i: number) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
    )}
  </div>
));

const ReasoningStepSchema = z.object({
  label: z.string(),
  status: z.enum(["pending", "running", "done", "error"]),
  durationMs: z.number().optional(),
});

const ReasoningTraceApi = {
  name: "ReasoningTrace",
  schema: z.object({ steps: z.array(ReasoningStepSchema) }),
};

const ReasoningTrace = createComponentImplementation(ReasoningTraceApi, ({ props }) => (
  <ol className="cardinal-research-trace">
    {props.steps.map((step, i) => (
      <li key={i} data-status={step.status}>
        {step.label}
        {step.durationMs !== undefined ? ` (${step.durationMs}ms)` : ""}
      </li>
    ))}
  </ol>
));

const CarCardApi = {
  name: "CarCard",
  schema: z.object({
    source: z.string(),
    sourceId: z.string(),
    rank: z.number(),
    score: z.number(),
    rationale: z.string(),
    headline: z.string().optional(),
    // D-060: the 3D asset standing in for this listing, resolved server-side by
    // `src/mcp/ui/vehicle_models.py`. Optional -- a card with no asset is still a valid card.
    modelSrc: z.string().optional(),
    posterSrc: z.string().optional(),
    // True when `modelSrc` is a body-style silhouette rather than a model of this actual car.
    representative: z.boolean().optional(),
    // A real reference photo of this model (vehicle_models.vehicle_photo_src), when sourced.
    // Takes over the poster slot below -- a real photo beats a generated GLB/silhouette still.
    photoSrc: z.string().optional(),
    // PLAN-02 P13 (proposal doc #4/#2): who is selling this, and what condition it is in.
    // Every one optional and mirrored in `src/mcp/ui/catalog.py`'s server-side spec -- a prop
    // registered on one side only is rejected by the other (CONSTITUTION II.4).
    dealerName: z.string().optional(),
    dealerCity: z.string().optional(),
    dealerRating: z.number().optional(),
    dealerVerified: z.boolean().optional(),
    condition: z.string().optional(),
    // PLAN-02 P14: what an add-to-cart click on this card means. Read off the listing
    // server-side (`CardVisual.offer_type`), never guessed here -- a card that assumed `buy`
    // for a rental-only listing would render a button whose click always 409s.
    offerType: z.string().optional(),
  }),
};

const CONDITION_LABEL: Record<string, string> = {
  new: "New",
  used: "Used",
  certified_pre_owned: "Certified pre-owned",
};

/**
 * A real reference photo of the model, with click-to-fullscreen.
 *
 * Rendered as an actual `<img>` rather than handed to `<model-viewer poster>`: a poster is
 * letterboxed into the viewer's own aspect box (which is what made a wide photo show up as a
 * small centred square), and it can't be opened. This fills the card's visual slot and blows
 * up to fit the screen on click.
 *
 * The overlay goes through a portal to `document.body` on purpose -- `.cardinal-car-card`
 * runs a `transform`-based entry animation, and a transformed ancestor becomes the containing
 * block for `position: fixed`, so an in-place overlay would be trapped inside the card.
 */
function CarPhoto({ src, alt }: { src: string; alt: string }): React.ReactElement {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    // The page behind a fullscreen image should not scroll under it.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  return (
    <>
      {/* stopPropagation throughout: the whole card is already an `explain` click target, and
          opening a photo must not also fire the score-breakdown round-trip. */}
      <button
        type="button"
        className="cardinal-car-photo-button"
        aria-label={`View full-screen photo of ${alt}`}
        onClick={(event) => {
          event.stopPropagation();
          setOpen(true);
        }}
      >
        <img className="cardinal-car-photo" src={src} alt={alt} loading="lazy" />
      </button>
      {open &&
        createPortal(
          <div
            className="cardinal-lightbox"
            role="dialog"
            aria-modal="true"
            aria-label={alt}
            onClick={(event) => {
              event.stopPropagation();
              setOpen(false);
            }}
          >
            <img className="cardinal-lightbox-image" src={src} alt={alt} />
            <button
              type="button"
              className="cardinal-lightbox-close"
              aria-label="Close full-screen photo"
              onClick={(event) => {
                event.stopPropagation();
                setOpen(false);
              }}
            >
              ✕
            </button>
          </div>,
          document.body,
        )}
    </>
  );
}

// Clicking a card dispatches an `explain` action through `ComponentContext.dispatchAction`
// (PHASE-6 SS6's action round-trip) -- `App.tsx`'s `postAction` relays it to
// `POST /sessions/{id}/actions`, which in a DEMO_MODE session pushes back the real
// `ScoreBreakdown` `rank()` already computed for this listing (no recomputation, D-026).
const CarCard = createComponentImplementation(CarCardApi, ({ props, context }) => (
  <article
    className="cardinal-car-card"
    data-rank={props.rank}
    // `--rank` (styles.css's staggered `card-in` animation-delay) rather than reading
    // `data-rank` back with `attr()`: calc() over attr() has no reliable cross-browser
    // support for anything but the `content` property, so the value has to arrive as a real
    // custom property instead.
    style={{ "--rank": props.rank } as React.CSSProperties}
    role="button"
    tabIndex={0}
    onClick={() =>
      context.dispatchAction({
        event: { name: "explain", context: { source: props.source, sourceId: props.sourceId } },
      })
    }
  >
    {(props.photoSrc || props.modelSrc) && (
      <div className="cardinal-car-viewer">
        {/*
          A real photo of the model wins the visual slot when one was sourced. Below it, the
          3D viewer is kept only when `modelSrc` is a model of this actual car -- for the far
          more common silhouette case the photo already says everything a generic body-style
          shape would, and stacking both just makes the card taller.

          `reveal="interaction"` and an always-present `poster` are gate 6.8's requirement for
          any list context: N cards on screen must not mean N GLB downloads before the user
          has shown interest in any of them. `auto-rotate` stays off here for the same reason
          -- PHASE-6 SS5 reserves it for a dedicated full-screen explainer surface.
        */}
        {props.photoSrc && (
          <CarPhoto
            src={props.photoSrc}
            alt={props.headline ?? `${props.source}:${props.sourceId}`}
          />
        )}
        {props.modelSrc && !(props.photoSrc && props.representative) && (
          <model-viewer
            src={props.modelSrc}
            poster={props.posterSrc}
            alt={props.headline ?? `${props.source}:${props.sourceId}`}
            camera-controls
            reveal="interaction"
            shadow-intensity="1"
            environment-image="neutral"
          />
        )}
        <p className="cardinal-representative-label">
          {props.photoSrc
            ? "Representative photo of this model -- not this specific vehicle."
            : props.representative
              ? "Body style shown for reference -- not this specific vehicle."
              : "Representative model -- not this specific vehicle."}
        </p>
      </div>
    )}
    <h3>
      #{props.rank} {props.headline ?? `${props.source}:${props.sourceId}`}
    </h3>
    {props.condition && (
      <span className="cardinal-condition" data-condition={props.condition}>
        {CONDITION_LABEL[props.condition] ?? props.condition}
      </span>
    )}
    <p className="cardinal-score">score {props.score.toFixed(2)}</p>
    <p className="cardinal-rationale">{props.rationale}</p>
    {/* PLAN-02 P13: dealer attribution. Rendered only when the listing actually resolves to
        a dealer -- an empty "Sold by" line reads as a bug, and a missing one reads as a card
        that predates the P13 re-seed, which is what it is. */}
    {props.dealerName && (
      <p className="cardinal-dealer" data-testid="car-card-dealer">
        <span className="cardinal-dealer-name">{props.dealerName}</span>
        {props.dealerCity && <span className="cardinal-dealer-city">{props.dealerCity}</span>}
        {props.dealerRating !== undefined && (
          <span className="cardinal-dealer-rating">{props.dealerRating.toFixed(1)}★</span>
        )}
        {/* Verified is a positive claim; anything else is stated as unverified rather than
            left blank. Silence about who you are paying is the thing P14's payee disclosure
            exists to prevent, and the card is the first place that question comes up. */}
        <span
          className="cardinal-dealer-verified"
          data-verified={props.dealerVerified === true ? "yes" : "no"}
        >
          {props.dealerVerified === true ? "Verified dealer" : "Unverified"}
        </span>
      </p>
    )}
    {/* PLAN-02 P14. Dispatched through P6's existing action round-trip -- the same
        `dispatchAction` -> `POST /sessions/{id}/actions` path gate 6.5 already proves -- and
        NOT a second channel. `App.tsx`'s handler is what turns it into an authenticated
        `POST /cart/items`, using the buyer's own httpOnly cookie: a credential this browser
        has and the agent process does not, which is what makes gate 14.7 ("no agent-driven
        path adds to cart") a property of where the credential lives rather than a rule
        somebody has to enforce.

        `stopPropagation` because the whole card is already an `explain` click target -- an
        add that also expanded the score breakdown would look like a misfire. */}
    {props.offerType && (
      <button
        type="button"
        className="cardinal-add-to-cart"
        data-testid={`add-to-cart-${props.source}-${props.sourceId}`}
        onClick={(event) => {
          event.stopPropagation();
          context.dispatchAction({
            event: {
              name: "add_to_cart",
              context: {
                source: props.source,
                sourceId: props.sourceId,
                offerType: props.offerType,
              },
            },
          });
        }}
      >
        {props.offerType === "rent" ? "Add to cart to rent" : "Add to cart"}
      </button>
    )}
  </article>
));

const CriterionSchema = z.object({
  name: z.string(),
  weight: z.number(),
  value: z.number(),
  contribution: z.number(),
});

const ScoreBreakdownApi = {
  name: "ScoreBreakdown",
  schema: z.object({
    criteria: z.array(CriterionSchema),
    source: z.string().optional(),
    sourceId: z.string().optional(),
  }),
};

/**
 * Renders at 0% for one frame, then the real value -- `styles.css`'s `.cardinal-criterion-fill`
 * transition needs an actual "from" state to animate out of. Setting the target width directly
 * on first paint (the previous shape) gives CSS nothing to transition from, so it just appears
 * at full length instead of growing into it.
 */
function SpringBar({ targetPct }: { targetPct: number }): React.ReactElement {
  const [pct, setPct] = useState(0);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setPct(targetPct));
    return () => cancelAnimationFrame(frame);
  }, [targetPct]);
  return <div className="cardinal-criterion-fill" style={{ width: `${pct}%` }} />;
}

const ScoreBreakdown = createComponentImplementation(ScoreBreakdownApi, ({ props }) => (
  <div className="cardinal-score-breakdown">
    {props.criteria.map((c) => (
      <div key={c.name} className="cardinal-criterion-bar">
        <span className="cardinal-criterion-name">{c.name}</span>
        <SpringBar targetPct={Math.round(c.value * 100)} />
        <span className="cardinal-criterion-contribution">
          {c.contribution.toFixed(3)}
        </span>
      </div>
    ))}
  </div>
));

const TcoLineSchema = z.object({
  kind: z.string(),
  amountEur: z.number(),
  note: z.string().optional(),
});

const TcoSeriesEntrySchema = z.object({
  source: z.string(),
  sourceId: z.string(),
  path: z.string().optional(),
  total: z.number().optional(),
  totalCostEur: z.number().optional(),
  lines: z.array(TcoLineSchema).optional(),
});

const TcoChartApi = {
  name: "TcoChart",
  schema: z.object({
    series: z.array(TcoSeriesEntrySchema),
    breakEvenMonth: z.number().optional(),
  }),
};

const RADAR_SIZE = 190;
const RADAR_CENTER = RADAR_SIZE / 2;
const RADAR_RADIUS = 66;
const RADAR_COLORS = ["#4ade9b", "#60a5fa", "#f59e0b"];

function polarPoint(angle: number, radius: number): [number, number] {
  return [RADAR_CENTER + radius * Math.sin(angle), RADAR_CENTER - radius * Math.cos(angle)];
}

type TcoSeries = z.infer<typeof TcoSeriesEntrySchema>;

/**
 * A 5(ish)-axis radar of buy vs. rent's own itemised cost lines -- purely a client-side
 * reshaping of data the schema already carries (`series[].lines`), no backend change. Each
 * axis is normalised to its own max across the plotted series (a raw EUR radar would be
 * dominated by whichever line happens to be the largest, e.g. purchase price swamping
 * insurance), which is what a real radar chart does and is why one axis "maxing out" means
 * "highest on this line," not "highest overall."
 *
 * Returns nothing rather than a degenerate shape when there's too little to plot -- a
 * two-point or one-point "polygon" is not a chart, just noise next to the real numbers below.
 */
function TcoRadar({ series }: { series: TcoSeries[] }): React.ReactElement | null {
  const withLines = series.filter((s) => s.lines && s.lines.length > 0);
  if (withLines.length === 0) return null;

  const axes = Array.from(new Set(withLines.flatMap((s) => s.lines!.map((l) => l.kind))));
  if (axes.length < 3) return null;

  const maxByAxis = new Map(
    axes.map((axis) => [
      axis,
      Math.max(1, ...withLines.map((s) => s.lines!.find((l) => l.kind === axis)?.amountEur ?? 0)),
    ]),
  );
  const angleStep = (2 * Math.PI) / axes.length;
  const gridLevels = [0.25, 0.5, 0.75, 1];

  return (
    <div>
      <div className="cardinal-tco-radar-legend">
        {withLines.map((s, i) => (
          <span key={i}>
            <span
              className="cardinal-tco-radar-swatch"
              style={{ background: RADAR_COLORS[i % RADAR_COLORS.length] }}
            />
            {s.path ?? `${s.source}:${s.sourceId}`}
          </span>
        ))}
      </div>
      <svg
        className="cardinal-tco-radar"
        width={RADAR_SIZE}
        height={RADAR_SIZE}
        viewBox={`0 0 ${RADAR_SIZE} ${RADAR_SIZE}`}
        role="img"
        aria-label="Cost-category comparison radar"
      >
        {gridLevels.map((level) => (
          <polygon
            key={level}
            className="cardinal-tco-radar-grid"
            points={axes.map((_, i) => polarPoint(i * angleStep, RADAR_RADIUS * level).join(",")).join(" ")}
          />
        ))}
        {axes.map((axis, i) => {
          const [x, y] = polarPoint(i * angleStep, RADAR_RADIUS);
          return (
            <line
              key={axis}
              className="cardinal-tco-radar-axis"
              x1={RADAR_CENTER}
              y1={RADAR_CENTER}
              x2={x}
              y2={y}
            />
          );
        })}
        {withLines.map((s, si) => {
          const points = axes
            .map((axis, i) => {
              const value = s.lines!.find((l) => l.kind === axis)?.amountEur ?? 0;
              const ratio = value / (maxByAxis.get(axis) ?? 1);
              return polarPoint(i * angleStep, RADAR_RADIUS * ratio).join(",");
            })
            .join(" ");
          const color = RADAR_COLORS[si % RADAR_COLORS.length];
          return (
            <polygon
              key={si}
              className="cardinal-tco-radar-poly"
              points={points}
              style={{ stroke: color, fill: color, animationDelay: `${si * 150}ms` }}
            />
          );
        })}
        {axes.map((axis, i) => {
          const [x, y] = polarPoint(i * angleStep, RADAR_RADIUS + 16);
          return (
            <text
              key={axis}
              className="cardinal-tco-radar-label"
              x={x}
              y={y}
              textAnchor="middle"
              dominantBaseline="middle"
            >
              {axis.replace(/_/g, " ")}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

const TcoChart = createComponentImplementation(TcoChartApi, ({ props, context }) => {
  const hasLines = props.series.some((s) => s.lines && s.lines.length > 0);
  return (
    <div className="cardinal-tco-chart">
      <TcoRadar series={props.series} />
      {props.series.map((entry, i) => (
        <div key={i} className="cardinal-tco-series" data-path={entry.path}>
          <strong>{entry.path ?? `${entry.source}:${entry.sourceId}`}</strong>
          <span>EUR {(entry.total ?? entry.totalCostEur ?? 0).toLocaleString()}</span>
          {entry.lines && (
            <ul>
              {entry.lines.map((line, j) => (
                <li key={j}>
                  {line.kind}: EUR {line.amountEur.toLocaleString()}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
      {props.breakEvenMonth !== undefined && (
        <p className="cardinal-break-even">Break-even: month {props.breakEvenMonth}</p>
      )}
      {/* Only the summary form (`render_tco`'s own frozen schema, PHASE-6) is ever the first
          thing on screen -- itemised `lines` only arrive via this click, which reaches
          `demo_stream.handle_expand_tco_action` the same round-trip `CarCard`'s `explain`
          already proves out (PHASE-6 SS6, D-026's no-recomputation rule, reused). */}
      {!hasLines && (
        <button
          type="button"
          className="cardinal-tco-expand"
          onClick={() => context.dispatchAction({ event: { name: "expand_tco", context: {} } })}
        >
          See itemised cost breakdown →
        </button>
      )}
    </div>
  );
});

const AnnotationSchema = z.object({
  hotspot: z.string(),
  label: z.string(),
  text: z.string(),
});

const PowertrainExplainerApi = {
  name: "PowertrainExplainer",
  schema: z.object({
    archetype: z.string(),
    modelSrc: z.string(),
    posterSrc: z.string(),
    annotations: z.array(AnnotationSchema).optional(),
  }),
};

/**
 * `<model-viewer>` (PHASE-6 SS5): one element, free lighting/shadows/orbit/AR. `poster` is
 * always set (gate 6.8) so something renders instantly while the GLB streams, and
 * `reveal="interaction"` here (list/detail context) defers the actual model load until the
 * user engages it -- a dedicated full-screen explainer surface would set `auto-rotate`
 * instead, which PHASE-6 SS5 reserves for that context only.
 */
const PowertrainExplainer = createComponentImplementation(PowertrainExplainerApi, ({ props }) => (
  <div className="cardinal-powertrain-explainer" data-archetype={props.archetype}>
    <model-viewer
      src={props.modelSrc}
      poster={props.posterSrc}
      camera-controls
      reveal="interaction"
      ar
      ar-modes="webxr scene-viewer quick-look"
      shadow-intensity="1"
      environment-image="neutral"
    >
      {(props.annotations ?? []).map((a: { hotspot: string; label: string; text: string }) => (
        <button key={a.hotspot} slot={`hotspot-${a.hotspot}`} className="cardinal-hotspot">
          {a.label}
          <span className="cardinal-hotspot-text">{a.text}</span>
        </button>
      ))}
    </model-viewer>
    <p className="cardinal-representative-label">
      Representative image -- not this specific vehicle.
    </p>
  </div>
));

const CompareTableApi = {
  name: "CompareTable",
  schema: z.object({
    listings: z.array(z.object({ source: z.string(), sourceId: z.string() })),
    fields: z.array(z.string()),
    rows: z.array(z.object({ field: z.string(), values: z.array(z.string()) })),
  }),
};

const CompareTable = createComponentImplementation(CompareTableApi, ({ props }) => (
  <table className="cardinal-compare-table">
    <thead>
      <tr>
        <th />
        {props.listings.map((l) => (
          <th key={l.sourceId}>{l.sourceId}</th>
        ))}
      </tr>
    </thead>
    <tbody>
      {props.rows.map((row) => (
        <tr key={row.field}>
          <th>{row.field}</th>
          {row.values.map((v, i) => (
            <td key={i}>{v}</td>
          ))}
        </tr>
      ))}
    </tbody>
  </table>
));

const Vehicle360Api = {
  name: "Vehicle360",
  schema: z.object({
    frames: z.array(z.string()),
    hotspots: z.array(z.object({ label: z.string() })).optional(),
  }),
};

// [SCALE] -- registered so `compose_surface` can validate a tree naming it; not emitted by
// the [MVP] compiler (PROGRESS.md). A static turntable frame stands in for the real
// image-sequence player PHASE-6 SS5 describes.
const Vehicle360 = createComponentImplementation(Vehicle360Api, ({ props }) => (
  <div className="cardinal-vehicle-360">
    {props.frames[0] && <img src={props.frames[0]} alt="Vehicle turntable, frame 1" />}
  </div>
));

const RelaxationOptionsApi = {
  name: "RelaxationOptions",
  schema: z.object({
    constraint: z.string(),
    delta: z.string(),
    candidatesUnlocked: z.number(),
  }),
};

// [SCALE] -- registered for the same reason as Vehicle360 (PHASE-5's counterfactual solver,
// gate 5.10, is not built yet).
const RelaxationOptions = createComponentImplementation(RelaxationOptionsApi, ({ props }) => (
  <div className="cardinal-relaxation-options">
    Raising {props.constraint} by {props.delta} unlocks {props.candidatesUnlocked} more option(s).
  </div>
));

export const customComponents: ReactComponentImplementation[] = [
  InterviewProgress,
  ReasoningTrace,
  CarCard,
  ScoreBreakdown,
  TcoChart,
  PowertrainExplainer,
  CompareTable,
  Vehicle360,
  RelaxationOptions,
];
