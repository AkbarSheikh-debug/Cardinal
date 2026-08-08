# PHASE 6 — Generative UI (A2UI)

**Owns:** everything the agent draws. The component catalog, the compiler that turns semantic tool
calls into A2UI messages, the transport, the escape hatch, and the 3D layer.

The brief's most-missed requirement. Most teams will build a React app and claim the agent drives
it; A2UI is a real wire protocol with a real renderer, and using it properly is visible and
verifiable.

---

## 1. Objective

Agent-composed, catalog-validated, progressively-streamed surfaces — with a validated escape hatch
for layouts the agent invents.

## 2. Scope

### In
- `[MVP]` `carCatalog` — custom component set (§3)
- `[MVP]` A2UI compiler: semantic tool call → `createSurface` / `updateComponents` / `updateDataModel`
- `[MVP]` SSE transport + surface lifecycle
- `[MVP]` `compose_surface` escape hatch with server-side validation
- `[MVP]` Action round-trip: renderer `actionHandler` → backend → agent session
- `[MVP]` `PowertrainExplainer` — 3D, 8 archetypes
- `[SCALE]` `Vehicle360` — image-sequence turntable of the actual vehicle
- `[SCALE]` Progressive/streaming render as the agent composes
- `[SCALE]` Theme propagation, reduced-motion, full a11y pass

### Out
- MCP App iframes — P7. Different protocol, different trust boundary, deliberately not conflated.

---

## 3. The catalog

A2UI's security model is **client-enforced catalogs**: the renderer only draws components it knows,
so the agent cannot inject arbitrary markup. Our catalog extends `basicCatalog`.

| Component | Props | Emitted when |
|---|---|---|
| `InterviewProgress` | slots, confidences, phase | Every INTERVIEW turn |
| `ReasoningTrace` | steps[] with status + duration | During RESEARCH |
| `CarCard` | listing summary, score, rank | Results list |
| `ScoreBreakdown` | criteria[], weights, contributions | Expanded card — a direct render of P5's `ScoreBreakdown` |
| `CompareTable` | listings[], aligned fields | User asks to compare |
| `TcoChart` | series, break-even month, line items | Rent-vs-buy answer |
| `PowertrainExplainer` | archetype, annotations[] | Agent judges an explanation is warranted |
| `Vehicle360` | frame sequence, hotspots | Listing detail (`[SCALE]`) |
| `RelaxationOptions` | constraint, delta, candidates_unlocked | Zero-result path |

Registration (verified v0.9 API):

```tsx
import { z } from 'zod';
import { CommonSchemas } from '@a2ui/web_core/v0_9';
import { createComponentImplementation } from '@a2ui/react/v0_9';

const ScoreBreakdownApi = {
  name: 'ScoreBreakdown',
  schema: z.object({
    criteria: z.array(z.object({
      name: CommonSchemas.DynamicString,
      weight: CommonSchemas.DynamicNumber,
      value: CommonSchemas.DynamicNumber,
      contribution: CommonSchemas.DynamicNumber,
    })),
    onExplain: CommonSchemas.Action,
  }),
};
```

**Everything A2UI-facing lives behind one adapter module.** The protocol is at v0.9 with v1.0 in
candidate; when it moves, exactly one file changes. Import from the versioned path
(`@a2ui/react/v0_9`), pin exact versions, and never scatter `MessageProcessor` calls through
components.

---

## 4. The compiler, and the escape hatch

### Why hybrid

Two naive options, both wrong:

- **Agent emits raw A2UI JSON.** Maximally generative; an LLM producing a valid flat component graph
  with correct data-model paths *every turn* will fail under demo conditions, and it's slow.
- **Backend renders everything.** Reliable; not agent-driven UI, and anyone who knows A2UI sees
  through it in ten seconds.

### The hybrid

Semantic tools, deterministically compiled:

```python
@tool("render_results", "Show the user your ranked recommendations. Call this once you have "
      "a ranking from the scorer — do not describe results in prose instead. Include a "
      "rationale per listing; the UI renders the score breakdown from the scorer's output.",
      {"listing_ids": list[str], "weights": dict[str, float], "rationales": dict[str, str]})
async def render_results(args) -> dict:
    surface = compile_results_surface(args)     # pure function, unit-tested
    await sse.push(session_id, surface.messages)
    return {"content": [{"type": "text", "text": f"Rendered {len(args['listing_ids'])} results."}]}
```

Plus **one escape hatch** — `compose_surface(components, data_model)` — accepting a real component
tree from the model, validated server-side against the catalog schema before forwarding. Use it for
genuinely novel layouts: an ad-hoc comparison the agent invents, a bespoke explainer.

Validation rejects: unknown component names, props failing the Zod schema, dangling `children`
references, duplicate ids, malformed data-model paths, and depth > 8. **Rejection returns an error
to the model as a tool result** so it can retry with a correction — it never forwards partial or
repaired output to the renderer.

That combination gives real generative UI where novelty matters and a reliable backbone everywhere
else. Say this in the deck: it reads as engineering judgement, not a shortcut.

---

## 5. The 3D layer — what's worth building

### The honest position

**Per-listing 3D car models don't survive into production.** Every serious used-car marketplace —
Carvana, Cazoo, AutoTrader — uses 360° photography of the actual vehicle. OEM configurators use 3D
legitimately, but only for *new* cars, where the model set is finite and the job is configuring
options. Three reasons the marketplace case fails:

1. **It misrepresents the product.** A generic "sports coupe" GLB standing in for a specific 2022
   GR86 with 41,200 km hides the wear, the wheels, and the damage a used-car buyer is specifically
   trying to assess. In most jurisdictions that's a consumer-protection issue, not a design choice.
2. **Asset economics.** Accurate licensed models run $200–2,000 each; 24 brands × models × years is
   hundreds of assets that go stale annually.
3. **Mobile.** Most car shopping happens on a phone on mobile data.

### What to build instead

| Surface | Mechanism | Status |
|---|---|---|
| Per-listing visual | `Vehicle360` — image-sequence turntable of the real car, the industry-correct pattern | `[SCALE]` |
| Powertrain explanation | `PowertrainExplainer` — **8 3D archetypes** | `[MVP]` |

**`PowertrainExplainer` is the version of this idea worth shipping.** Eight archetypes cover every
vehicle sold: I3-turbo, I4 naturally aspirated, I4 turbo, V6, V8, hybrid (series/parallel), PHEV,
BEV skateboard. Finite, cheap, never stale, and — critically — it misrepresents nothing, because it
depicts a *category*, not a specific car.

And it's genuinely useful. A cutaway that shows why a timing belt means a €900 service at 100,000 km
while a chain doesn't, or why a BEV skateboard has no transmission to fail, is decision-relevant
information that nobody presents visually. It feeds directly from P1's `timing_mechanism` and
`powertrain_archetype` fields and P5's maintenance line in the TCO.

The agent decides *when* an explanation is warranted and emits the component — which is exactly what
"agent-driven dynamic interface" is supposed to mean, as opposed to a static detail page that
happens to contain a canvas.

### Implementation

`<model-viewer>` — one element, free lighting, shadows, orbit, poster fallback, and AR on mobile:

```html
<model-viewer src="/models/powertrain/i4-turbo.glb" poster="/models/powertrain/i4-turbo.webp"
              camera-controls auto-rotate ar ar-modes="webxr scene-viewer quick-look"
              shadow-intensity="1" environment-image="neutral" reveal="interaction"></model-viewer>
```

Asset discipline, enforced by a gate:

- Draco: `npx @gltf-transform/cli optimize in.glb out.glb --compress draco --texture-size 1024`
- **≤2 MB per model**, 8 models, ~16 MB total ceiling
- `poster` always set — something renders instantly while the GLB streams
- `reveal="interaction"` in lists; auto-rotate only in a dedicated detail surface
- Hotspot annotations (`<button slot="hotspot-belt">`) carry the explanation text, so the 3D is
  labelled rather than decorative

For the hackathon, archetype car GLBs may stand in for listing visuals — **labelled "representative
image"** in the UI. That label is not optional.

---

## 6. Transport and lifecycle

SSE for agent→client, POST for client→agent. Simpler than WebSockets, survives proxies, matches
A2UI's documented transports.

Surface lifecycle matters more than it looks: `createSurface` once per logical view, then
`updateComponents` / `updateDataModel` to mutate. Re-creating a surface every turn destroys scroll
position, loses focus, and makes the UI flicker — which reads as "prototype" instantly.

Actions flow back through the renderer's `actionHandler` → POST `/actions` → injected into the agent
session as a user turn with structured provenance (`{surface, component, action, payload}`), so the
agent knows a click happened rather than inferring it from prose.

---

## 7. Exit gate

`scripts/gate_phase6.py`:

| # | Criterion |
|---|---|
| 6.1 | Every message the compiler emits validates against the catalog schema |
| 6.2 | Golden-message fixtures render in a headless browser with **zero** console errors or warnings |
| 6.3 | `compose_surface` with an unknown component is rejected; the error reaches the model as a tool result; nothing is forwarded to the renderer |
| 6.4 | `compose_surface` with a dangling child reference, a duplicate id, and depth > 8 are each rejected |
| 6.5 | Action round-trip: a simulated click reaches the agent session with full provenance |
| 6.6 | Surface identity is stable — a second `render_results` in the same session updates, does not recreate |
| 6.7 | All 8 powertrain GLBs are ≤2 MB; total asset bundle ≤16 MB |
| 6.8 | Every `<model-viewer>` has a `poster`; list contexts use `reveal="interaction"` |
| 6.9 | All A2UI imports are from `@a2ui/*/v0_9`; exactly one module imports `MessageProcessor` |
| 6.10 | Reduced-motion honoured; every interactive element has a visible focus state (`[SCALE]`) |

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| A2UI v0.9 → v1.0 breaks the renderer | Pin exact versions; single adapter module (gate 6.9); v1.0 adds `actionResponse` RPC and `surfaceProperties` — additive, but verify before bumping |
| `compose_surface` becomes the default path and reliability drops | Semantic tools have prescriptive descriptions telling the model to prefer them; measure the ratio in P9 evals and alert if escape-hatch use exceeds 15% of renders |
| GLB assets blow page weight | Gate 6.7 hard-fails the build |
| Judges read the 3D as gimmick | Lead with `PowertrainExplainer` in the demo, not the car turntable. Explanation beats decoration. |
| Surface re-creation causes flicker | Gate 6.6 |
