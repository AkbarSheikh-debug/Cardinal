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
  }),
};

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
    {props.modelSrc && (
      <div className="cardinal-car-viewer">
        {/*
          `reveal="interaction"` and a always-present `poster` are gate 6.8's requirement for
          any list context: N cards on screen must not mean N GLB downloads before the user
          has shown interest in any of them. `auto-rotate` stays off here for the same reason
          -- PHASE-6 SS5 reserves it for a dedicated full-screen explainer surface.
        */}
        <model-viewer
          src={props.modelSrc}
          poster={props.posterSrc}
          alt={props.headline ?? `${props.source}:${props.sourceId}`}
          camera-controls
          reveal="interaction"
          shadow-intensity="1"
          environment-image="neutral"
        />
        <p className="cardinal-representative-label">
          {props.representative
            ? "Body style shown for reference -- not this specific vehicle."
            : "Representative model -- not this specific vehicle."}
        </p>
      </div>
    )}
    <h3>
      #{props.rank} {props.headline ?? `${props.source}:${props.sourceId}`}
    </h3>
    <p className="cardinal-score">score {props.score.toFixed(2)}</p>
    <p className="cardinal-rationale">{props.rationale}</p>
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
