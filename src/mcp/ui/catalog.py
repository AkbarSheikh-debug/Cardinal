"""The `carCatalog` component registry (PHASE-6 SS3): the Python-side mirror of the Zod
schemas registered on the client via `createComponentImplementation` (`web/src/a2ui/catalog.tsx`).

A2UI's security model is client-enforced catalogs -- the renderer only draws components it
knows. This module is the server-side half of that same discipline: `compose_surface`
(CONSTITUTION II.4) is validated against exactly this registry before anything is forwarded,
so a tree the *client* would refuse to draw is rejected here first, with a clear reason,
rather than reaching the wire at all.

`CardinalCatalog` extends `basicCatalog` (PHASE-6 SS3) -- so this registry carries both the
handful of basic layout/content primitives our compiler itself uses (`Column`, `Row`, `Card`,
`Text`, `Divider`) and the nine custom components PHASE-6 SS3's table defines. It is not a
full mirror of `basicCatalog` (that has ~18 components); only the ones our own compiler or a
plausible `compose_surface` tree would ever reach for are registered, and an unregistered
basic-catalog component is correctly rejected as UNKNOWN_COMPONENT -- the same outcome a
client-side catalog miss would produce.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

#: PHASE-6 SS3: "when [A2UI] moves, exactly one file changes" -- the catalog id is versioned
#: alongside the pinned `v0_9` import path it travels with.
CATALOG_ID = "cardinal.dev:carCatalog"

#: PHASE-6 SS4: `compose_surface` rejects a tree deeper than this.
MAX_TREE_DEPTH = 8

#: Present on every component regardless of its own spec (`common_types.json#ComponentCommon`
#: / `CatalogComponentCommon`) -- never flagged as an unknown prop.
STRUCTURAL_KEYS = frozenset({"id", "component", "accessibility", "weight"})


class ChildArity(StrEnum):
    NONE = "none"
    SINGLE = "single"  # a `child` field: one ComponentId
    LIST = "list"  # a `children` field: ComponentId[] or a {componentId, path} template


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    required_props: frozenset[str] = field(default_factory=frozenset)
    optional_props: frozenset[str] = field(default_factory=frozenset)
    child_arity: ChildArity = ChildArity.NONE
    child_field: str | None = None

    @property
    def known_props(self) -> frozenset[str]:
        return self.required_props | self.optional_props


def _spec(
    name: str,
    *,
    required: tuple[str, ...] = (),
    optional: tuple[str, ...] = (),
    child_arity: ChildArity = ChildArity.NONE,
) -> ComponentSpec:
    child_field = {"single": "child", "list": "children"}.get(child_arity.value)
    return ComponentSpec(
        name=name,
        required_props=frozenset(required),
        optional_props=frozenset(optional),
        child_arity=child_arity,
        child_field=child_field,
    )


# -- a minimal slice of basicCatalog (PHASE-6 SS3's "extends basicCatalog") --------------------
# Only what our own compiler's layouts (and a plausible compose_surface escape-hatch tree)
# actually reach for. `web/src/a2ui/catalog.tsx` registers these from `@a2ui/react/v0_9`'s
# real basicCatalog rather than reimplementing them -- this registry only needs to know their
# *shape* well enough to validate a tree, not render one.
_BASIC: tuple[ComponentSpec, ...] = (
    _spec("Text", required=("text",), optional=("variant",)),
    _spec("Divider", optional=()),
    _spec("Card", required=("child",), child_arity=ChildArity.SINGLE),
    _spec(
        "Column",
        required=("children",),
        optional=("justify", "align"),
        child_arity=ChildArity.LIST,
    ),
    _spec(
        "Row", required=("children",), optional=("justify", "align"), child_arity=ChildArity.LIST
    ),
    _spec("Button", required=("label",), optional=("onClick", "variant")),
)

# -- the nine `carCatalog` components (PHASE-6 SS3's table) ------------------------------------
_CUSTOM: tuple[ComponentSpec, ...] = (
    # Every INTERVIEW turn: which slots are filled, which are open, and the phase.
    _spec("InterviewProgress", required=("slots", "phase"), optional=("reasoningTrace",)),
    # During RESEARCH: a trace of steps with status + duration.
    _spec("ReasoningTrace", required=("steps",)),
    # Results list: one listing summary, its score, and its rank. `headline` is optional --
    # `render_results`'s frozen P2 schema (src/mcp/ui/tools.py) carries a per-item rationale,
    # not a headline; a caller with a real `ListingSummary` on hand may supply one too.
    _spec(
        "CarCard",
        required=("source", "sourceId", "rank", "score", "rationale"),
        # `modelSrc`/`posterSrc`/`representative` are D-060's per-listing 3D. Optional, not
        # required: a card with no resolvable asset still renders as text, and the validator
        # would otherwise reject a perfectly good results surface for a missing picture.
        optional=(
            "headline",
            "modelSrc",
            "posterSrc",
            "representative",
            "onExplain",
            "onSelect",
        ),
    ),
    # Expanded card -- a direct render of P5's ScoreBreakdown (src/domain/scoring.py), no
    # recomputation. `criteria` mirrors PHASE-6 SS3's own worked registration example field
    # for field (name/weight/value/contribution); `source`/`sourceId` identify which listing
    # it belongs to, since a session may have more than one card expanded.
    _spec("ScoreBreakdown", required=("criteria",), optional=("onExplain", "source", "sourceId")),
    # User asks to compare: listings[] aligned on a shared set of fields.
    _spec("CompareTable", required=("listings", "fields", "rows")),
    # Rent-vs-buy answer: P5's TcoComparison (src/domain/tco.py), itemised, never estimated.
    _spec("TcoChart", required=("series",), optional=("breakEvenMonth",)),
    # PHASE-6 SS5: 8 finite archetypes, never a specific listing.
    _spec(
        "PowertrainExplainer",
        required=("archetype", "modelSrc", "posterSrc"),
        optional=("annotations",),
    ),
    # [SCALE] -- registered so an escape-hatch tree naming it fails on missing props, not on
    # UNKNOWN_COMPONENT; nothing in the P6 [MVP] compiler emits it yet (PROGRESS.md).
    _spec("Vehicle360", required=("frames",), optional=("hotspots",)),
    # Zero-result path -- [SCALE] (PHASE-5 SS7's counterfactual solver isn't built), registered
    # for the same reason as Vehicle360.
    _spec("RelaxationOptions", required=("constraint", "delta", "candidatesUnlocked")),
)

CATALOG: dict[str, ComponentSpec] = {spec.name: spec for spec in (*_BASIC, *_CUSTOM)}

#: The subset PHASE-6 SS5/SS10 fixes as exhaustive -- eight archetypes, never a ninth.
POWERTRAIN_ARCHETYPES: tuple[str, ...] = (
    "i3_turbo",
    "i4_na",
    "i4_turbo",
    "v6",
    "v8",
    "hybrid",
    "phev",
    "bev_skateboard",
)
