"""The five `ui-mcp` tools (PHASE-2 §4). Schemas frozen since P2; P6 fills the bodies in with
real handlers over the compiler (`src/mcp/ui/compiler.py`) and the catalog validator
(`src/mcp/ui/validate.py`).

Every handler compiles a real A2UI message, pushes it through the session's `UISink`
(PHASE-6 §6), and returns a short text summary as the tool result -- the model sees
confirmation that something rendered, never the wire payload itself, which stays on the
transport the browser actually reads.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from claude_agent_sdk import tool

from src.adapters.dealer_store import DealerDirectory
from src.adapters.store import ListingStore
from src.domain.enums import TimingMechanism
from src.domain.listing import Listing, ListingSummary
from src.mcp.audience import MODEL_ONLY, ToolSpec
from src.mcp.schema import strict_schema
from src.mcp.ui.compiler import (
    CardVisual,
    CompiledSurface,
    PowertrainProps,
    compile_detail_surface,
    compile_progress_surface,
    compile_results_surface,
    compile_tco_surface,
    to_messages,
)
from src.mcp.ui.sink import NullUISink, UISink
from src.mcp.ui.surfaces import SurfaceKind, SurfaceRegistry
from src.mcp.ui.validate import validate_component_tree
from src.mcp.ui.vehicle_models import (
    is_representative,
    vehicle_model_src,
    vehicle_photo_src,
    vehicle_poster_src,
)

PowertrainAssetPath = Callable[[str], str]


def _default_asset_path(archetype: str) -> str:
    return f"/models/powertrain/{archetype}.glb"


def _default_poster_path(archetype: str) -> str:
    return f"/models/powertrain/{archetype}.png"


def _powertrain_props(
    listing: Listing,
    *,
    model_src: PowertrainAssetPath = _default_asset_path,
    poster_src: PowertrainAssetPath = _default_poster_path,
) -> PowertrainProps:
    """Feeds directly off P1's `timing_mechanism` field (PHASE-6 §5): the annotation text is
    decision-relevant information ("a belt means a service event"), not decoration, and it is
    genuinely derived from this listing rather than boilerplate.
    """
    archetype = listing.powertrain_archetype.value
    if listing.timing_mechanism is TimingMechanism.NOT_APPLICABLE:
        annotations = (
            {
                "hotspot": "drivetrain",
                "label": "No timing belt or chain",
                "text": "Electric drivetrain -- no timing belt/chain service to schedule.",
            },
        )
    else:
        mechanism = listing.timing_mechanism.value
        interval = listing.service_interval_km
        text = (
            f"{mechanism.title()}-driven timing; service interval {interval:,} km."
            if interval
            else f"{mechanism.title()}-driven timing."
        )
        annotations = ({"hotspot": "timing", "label": mechanism.title(), "text": text},)
    return PowertrainProps(
        archetype=archetype,
        model_src=model_src(archetype),
        poster_src=poster_src(archetype),
        annotations=annotations,
    )


async def _card_visuals(
    store: ListingStore | None,
    args: dict[str, Any],
    dealers: DealerDirectory | None = None,
) -> dict[tuple[str, str], CardVisual]:
    """Resolves each ranked item to its headline and 3D asset (D-060), so the compiler stays
    a pure function of primitives and this module keeps the I/O.

    Best-effort by design: no store, or a listing that no longer resolves, simply yields no
    entry for that item and the card falls back to the text-only shape. A results surface that
    fails to render because an asset lookup missed would be a worse failure than a card
    without a picture.
    """
    if store is None:
        return {}
    visuals: dict[tuple[str, str], CardVisual] = {}
    for item in args.get("items", []):
        source, source_id = item["source"], item["source_id"]
        listing = await store.fetch(source, source_id)
        if listing is None:
            continue
        # PLAN-02 P13. Best-effort in exactly the same way the 3D asset lookup is: no
        # directory wired, or a listing that predates the P13 re-seed, yields a card with no
        # attribution rather than an error or a half-rendered "Sold by".
        dealer = None
        if dealers is not None and listing.dealer_id is not None:
            dealer = await dealers.get(listing.dealer_id)

        visuals[(source, source_id)] = CardVisual(
            headline=ListingSummary.from_listing(listing).headline,
            model_src=vehicle_model_src(listing.brand, listing.model, listing.category),
            poster_src=vehicle_poster_src(listing.brand, listing.model, listing.category),
            representative=is_representative(listing.brand, listing.model),
            photo_src=vehicle_photo_src(listing.brand, listing.model),
            condition=listing.condition.value,
            # PLAN-02 P14: read off the listing, never assumed -- see `CardVisual.offer_type`.
            offer_type=listing.offer_type.value,
            dealer_name=dealer.display_name if dealer else None,
            dealer_city=dealer.city if dealer else None,
            dealer_rating=float(dealer.rating) if dealer else None,
            dealer_verified=dealer.is_verified if dealer else None,
        )
    return visuals


def _text_result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _rejected(errors: list[str]) -> dict[str, Any]:
    """CONSTITUTION II.4: rejection reaches the model as a tool result it can retry from,
    never a partial or repaired render forwarded to the client.
    """
    return {
        "content": [{"type": "text", "text": "compose_surface rejected: " + "; ".join(errors)}],
        "is_error": True,
    }


def build_tool_specs(
    *,
    session_id: str = "unbound",
    sink: UISink | None = None,
    registry: SurfaceRegistry | None = None,
    store: ListingStore | None = None,
    dealers: DealerDirectory | None = None,
    phase: Callable[[], str] | None = None,
) -> list[ToolSpec]:
    """`session_id`/`sink`/`registry` are what gate 6.6's surface-identity guarantee runs on;
    `store`/`phase` are the two pieces of session context `render_detail`/`render_progress`
    need that P2's frozen tool schemas don't carry (a listing to describe, the true current
    phase) -- fetched here, at the seam, rather than the pure compiler functions reaching for
    them themselves.
    """
    sink = sink or NullUISink()
    registry = registry or SurfaceRegistry()
    phase_of: Callable[[], str] = phase or (lambda: "interview")

    _rationale_item = {
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "source_id": {"type": "string"},
            "rank": {"type": "integer", "minimum": 1},
            "score": {"type": "number"},
            "rationale": {
                "type": "string",
                "description": "Why this rank, grounded in cited listing fields.",
            },
        },
        "required": ["source", "source_id", "rank", "score", "rationale"],
        "additionalProperties": False,
    }

    @tool(
        "render_progress",
        "Draw the interview-progress surface: which requirement slots are filled, which "
        "are still open, and a short trace of what the agent is currently reasoning about. "
        "Call this when a turn changes the state of the interview -- a slot gets filled, "
        "confirmed, or corrected -- so the user can see the agent's understanding update "
        "live rather than only at the end. Do not call it on turns that changed nothing.",
        strict_schema(
            {
                "completed_slots": {"type": "array", "items": {"type": "string"}},
                "open_slots": {"type": "array", "items": {"type": "string"}},
                "reasoning_trace": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Short, human-readable notes on current reasoning.",
                },
            },
            required=["completed_slots", "open_slots"],
        ),
    )
    async def render_progress(args: dict[str, Any]) -> dict[str, Any]:
        compiled = compile_progress_surface(args, phase=phase_of())
        await sink.push(to_messages(session_id, compiled, registry))
        return _text_result(
            f"Rendered interview progress: {len(args.get('completed_slots', []))} filled, "
            f"{len(args.get('open_slots', []))} open."
        )

    @tool(
        "render_results",
        "Draw the ranked recommendation list: each candidate's rank, its deterministic "
        "score, the weights that produced it, and a per-listing rationale grounded in cited "
        "fields. Call this when the scorer has produced a ranking the user has not yet "
        "seen, or when weights change and the ranking is recomputed. Never call it with a "
        "rationale that contains a number not traceable to a listing field.",
        strict_schema(
            {
                "weights": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                    "description": "Named scoring criteria to their weight, chosen by the model.",
                },
                "items": {"type": "array", "items": _rationale_item, "minItems": 1},
            },
            required=["weights", "items"],
        ),
    )
    async def render_results(args: dict[str, Any]) -> dict[str, Any]:
        compiled = compile_results_surface(args, visuals=await _card_visuals(store, args, dealers))
        await sink.push(to_messages(session_id, compiled, registry))
        return _text_result(f"Rendered {len(args.get('items', []))} results.")

    @tool(
        "render_detail",
        "Draw the full-detail surface for one listing the user asked to see closely, "
        "optionally including the PowertrainExplainer cutaway. Call this when the user asks "
        "to see a specific candidate in depth, typically right after get_listing returns its "
        "full record for that same listing. Set show_powertrain_explainer only when the "
        "engine, drivetrain, or maintenance cost is actually relevant to what was asked.",
        strict_schema(
            {
                "source": {"type": "string"},
                "source_id": {"type": "string"},
                "show_powertrain_explainer": {
                    "type": "boolean",
                    "description": "Defaults to false.",
                },
            },
            required=["source", "source_id"],
        ),
    )
    async def render_detail(args: dict[str, Any]) -> dict[str, Any]:
        if store is None:
            return _text_result(
                f"render_detail has no listing store wired up for {args['source']}:"
                f"{args['source_id']}."
            )
        listing = await store.fetch(args["source"], args["source_id"])
        if listing is None:
            return {
                "content": [
                    {"type": "text", "text": f"No listing {args['source']}:{args['source_id']}."}
                ],
                "is_error": True,
            }
        summary = ListingSummary.from_listing(listing)
        price = listing.price_buy or listing.market_value
        powertrain = _powertrain_props(listing) if args.get("show_powertrain_explainer") else None
        compiled = compile_detail_surface(
            args,
            headline=summary.headline,
            price_display=f"EUR {price.amount:,.0f}",
            powertrain=powertrain,
        )
        await sink.push(to_messages(session_id, compiled, registry))
        return _text_result(f"Rendered detail for {summary.headline}.")

    @tool(
        "render_tco",
        "Draw a total-cost-of-ownership comparison across listings over a stated horizon, "
        "including the rent-versus-buy break-even point in months where one exists. Call "
        "this when the user is weighing running cost over time rather than sticker price "
        "alone -- most often right after asking 'should I rent or buy' in some form. Every "
        "figure shown must come from src/domain's TCO engine, never be estimated in prose.",
        strict_schema(
            {
                "horizon_months": {"type": "integer", "minimum": 1},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "source_id": {"type": "string"},
                            "total_cost_eur": {"type": "number"},
                        },
                        "required": ["source", "source_id", "total_cost_eur"],
                        "additionalProperties": False,
                    },
                    "minItems": 1,
                },
                "break_even_month": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Omit if buy and rent never cross within the horizon.",
                },
            },
            required=["horizon_months", "items"],
        ),
    )
    async def render_tco(args: dict[str, Any]) -> dict[str, Any]:
        compiled = compile_tco_surface(args)
        await sink.push(to_messages(session_id, compiled, registry))
        return _text_result(f"Rendered TCO over {args['horizon_months']} months.")

    @tool(
        "compose_surface",
        "The escape hatch: submit a real A2UI component tree for a case none of the fixed "
        "rendering tools cover. Call this when render_progress, render_results, "
        "render_detail and render_tco all genuinely do not fit what needs to be shown. The "
        "tree is validated server-side against the registered component catalog before it "
        "is ever forwarded to the client. An invalid tree comes back as a rejected tool "
        "result rather than being repaired or partially sent.",
        strict_schema(
            {
                "tree": {
                    "type": "object",
                    "description": (
                        "A component tree matching the A2UI catalog. Its internal shape is "
                        "validated server-side (PHASE-6 §4), not constrained here. Shape: "
                        "{'components': [{'id': ..., 'component': ..., ...props}, ...]}, "
                        "with exactly one component carrying id 'root'."
                    ),
                },
            },
        ),
    )
    async def compose_surface(args: dict[str, Any]) -> dict[str, Any]:
        tree = args.get("tree")
        components = tree.get("components") if isinstance(tree, dict) else None
        if not isinstance(components, list):
            return _rejected(["'tree' must be an object with a 'components' array"])
        errors = validate_component_tree(components)
        if errors:
            return _rejected([str(e) for e in errors])
        compiled = CompiledSurface(kind=SurfaceKind.COMPOSE, components=components)
        await sink.push(to_messages(session_id, compiled, registry))
        return _text_result(f"compose_surface accepted {len(components)} component(s).")

    return [
        ToolSpec(render_progress, MODEL_ONLY),
        ToolSpec(render_results, MODEL_ONLY),
        ToolSpec(render_detail, MODEL_ONLY),
        ToolSpec(render_tco, MODEL_ONLY),
        ToolSpec(compose_surface, MODEL_ONLY),
    ]
