"""Server-side validation of a component tree against `CATALOG` (CONSTITUTION II.4, PHASE-6
SS4/SS7). The one gate every message the compiler emits *and* every `compose_surface` escape
hatch call passes through before anything reaches the wire.

Rejection returns structured errors, never a partial or "repaired" tree -- CONSTITUTION II.4
is explicit that repair is not an option, only accept-whole or reject-whole.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.mcp.ui.catalog import CATALOG, MAX_TREE_DEPTH, STRUCTURAL_KEYS
from src.mcp.ui.messages import ComponentDict

ROOT_ID = "root"


@dataclass(frozen=True)
class ValidationError:
    code: str
    message: str
    component_id: str | None = None

    def __str__(self) -> str:
        where = f" ({self.component_id})" if self.component_id else ""
        return f"{self.code}{where}: {self.message}"


def _child_ids(component: ComponentDict, field_name: str) -> list[str]:
    """A `children`/`child` field is either a bare id, a list of ids, or a dynamic-list
    template (`{componentId, path}`, `common_types.json#/$defs/ChildList`) -- the template's
    own `componentId` still has to resolve to a real component, everything else about it
    (its `path`) is a data-model concern this module has no opinion on.
    """
    value = component.get(field_name)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        template_id = value.get("componentId")
        return [template_id] if isinstance(template_id, str) else []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def validate_component_tree(components: list[ComponentDict]) -> list[ValidationError]:
    """Every rule CONSTITUTION II.4 / PHASE-6 SS4 names: unknown component names, prop schema
    failures (missing required / unrecognised), dangling child references, duplicate ids,
    and depth > 8. Returns an empty list iff the tree is acceptable to forward as-is.
    """
    errors: list[ValidationError] = []

    if not components:
        return [
            ValidationError("EMPTY_TREE", "a component tree must contain at least one component")
        ]

    by_id: dict[str, ComponentDict] = {}
    seen_ids: set[str] = set()
    for c in components:
        cid = c.get("id")
        if not isinstance(cid, str) or not cid:
            errors.append(ValidationError("MISSING_ID", "component has no string 'id'"))
            continue
        if cid in seen_ids:
            errors.append(
                ValidationError("DUPLICATE_ID", f"id {cid!r} appears more than once", cid)
            )
            continue
        seen_ids.add(cid)
        by_id[cid] = c

    for cid, c in by_id.items():
        name = c.get("component")
        if not isinstance(name, str) or name not in CATALOG:
            errors.append(
                ValidationError(
                    "UNKNOWN_COMPONENT", f"{name!r} is not in the registered catalog", cid
                )
            )
            continue
        spec = CATALOG[name]
        # `child`/`children` are declared as required or optional props on the spec itself
        # (e.g. Column's `required=("children",)`), so they stay in `prop_keys` for both the
        # missing- and unknown-prop checks rather than being carved out as purely structural.
        prop_keys = set(c.keys()) - STRUCTURAL_KEYS
        missing = spec.required_props - prop_keys
        if missing:
            errors.append(
                ValidationError(
                    "MISSING_PROP", f"{name} is missing required prop(s) {sorted(missing)}", cid
                )
            )
        unknown = prop_keys - spec.known_props
        if unknown:
            errors.append(
                ValidationError(
                    "UNKNOWN_PROP", f"{name} has unrecognised prop(s) {sorted(unknown)}", cid
                )
            )

    if ROOT_ID not in by_id:
        errors.append(ValidationError("MISSING_ROOT", "no component has id 'root'"))

    for cid, c in by_id.items():
        name = c.get("component")
        maybe_spec = CATALOG.get(name) if isinstance(name, str) else None
        if maybe_spec is None or maybe_spec.child_field is None:
            continue
        for child_id in _child_ids(c, maybe_spec.child_field):
            if child_id not in by_id:
                errors.append(
                    ValidationError(
                        "DANGLING_CHILD",
                        f"references child {child_id!r}, which does not exist",
                        cid,
                    )
                )

    if ROOT_ID in by_id and not any(e.code in {"DANGLING_CHILD", "MISSING_ROOT"} for e in errors):
        depth_errors = _check_depth(by_id)
        errors.extend(depth_errors)

    return errors


def _check_depth(by_id: dict[str, ComponentDict]) -> list[ValidationError]:
    """Walks from `root` following child references. A cycle is reported the same way a
    too-deep tree is -- both mean "the renderer would never finish laying this out."
    """

    def depth_of(cid: str, visiting: frozenset[str]) -> int:
        if cid in visiting:
            raise _Cycle(cid)
        component = by_id.get(cid)
        if component is None:
            return 1
        name = component.get("component")
        spec = CATALOG.get(name) if isinstance(name, str) else None
        if spec is None or spec.child_field is None:
            return 1
        children = [c for c in _child_ids(component, spec.child_field) if c in by_id]
        if not children:
            return 1
        return 1 + max(depth_of(child, visiting | {cid}) for child in children)

    try:
        max_depth = depth_of(ROOT_ID, frozenset())
    except _Cycle as exc:
        return [ValidationError("CYCLE", f"child reference cycle through {exc.component_id!r}")]

    if max_depth > MAX_TREE_DEPTH:
        return [
            ValidationError(
                "DEPTH_EXCEEDED", f"tree depth {max_depth} exceeds the limit of {MAX_TREE_DEPTH}"
            )
        ]
    return []


class _Cycle(Exception):
    def __init__(self, component_id: str) -> None:
        super().__init__(component_id)
        self.component_id = component_id


def is_valid(components: list[ComponentDict]) -> bool:
    return not validate_component_tree(components)


def format_errors(errors: list[ValidationError]) -> str:
    return "; ".join(str(e) for e in errors)
