"""The `compose_surface` escape-hatch validator (CONSTITUTION II.4, PHASE-6 SS4/SS7),
tested directly against `src/mcp/ui/validate.py` -- `tests/unit/test_mcp_ui.py` exercises the
same rules through the real MCP tool call path; this file pins the validator's own rules in
isolation so a future catalog change that breaks one rule fails here, not just at the tool
boundary.
"""

from __future__ import annotations

from src.mcp.ui.validate import validate_component_tree


def _codes(components: list[dict[str, object]]) -> set[str]:
    return {e.code for e in validate_component_tree(components)}


def test_a_well_formed_tree_has_no_errors() -> None:
    components = [
        {"id": "root", "component": "Column", "children": ["a", "b"]},
        {"id": "a", "component": "Text", "text": "hi"},
        {
            "id": "b",
            "component": "CarCard",
            "source": "s",
            "sourceId": "1",
            "rank": 1,
            "score": 0.5,
            "rationale": "why",
        },
    ]
    assert validate_component_tree(components) == []


def test_unknown_component_name_is_rejected() -> None:
    assert "UNKNOWN_COMPONENT" in _codes([{"id": "root", "component": "NotReal"}])


def test_missing_required_prop_is_rejected() -> None:
    # Card requires 'child'.
    assert "MISSING_PROP" in _codes([{"id": "root", "component": "Card"}])


def test_unrecognised_prop_is_rejected() -> None:
    assert "UNKNOWN_PROP" in _codes(
        [{"id": "root", "component": "Text", "text": "hi", "somethingMadeUp": 1}]
    )


def test_duplicate_id_is_rejected() -> None:
    codes = _codes(
        [
            {"id": "root", "component": "Text", "text": "a"},
            {"id": "root", "component": "Text", "text": "b"},
        ]
    )
    assert "DUPLICATE_ID" in codes


def test_dangling_child_reference_is_rejected() -> None:
    assert "DANGLING_CHILD" in _codes([{"id": "root", "component": "Card", "child": "ghost"}])


def test_missing_root_is_rejected() -> None:
    assert "MISSING_ROOT" in _codes([{"id": "not-root", "component": "Text", "text": "hi"}])


def test_a_cycle_is_rejected() -> None:
    components = [
        {"id": "root", "component": "Card", "child": "a"},
        {"id": "a", "component": "Card", "child": "root"},
    ]
    assert "CYCLE" in _codes(components)


def test_depth_exactly_at_the_limit_is_accepted() -> None:
    # root -> n1 -> ... -> n7 -> leaf = 9 nodes = depth 9? Build exactly MAX_TREE_DEPTH deep.
    from src.mcp.ui.catalog import MAX_TREE_DEPTH

    chain_ids = ["root"] + [f"n{i}" for i in range(1, MAX_TREE_DEPTH - 1)] + ["leaf"]
    components = [
        {"id": chain_ids[i], "component": "Card", "child": chain_ids[i + 1]}
        for i in range(len(chain_ids) - 1)
    ]
    components.append({"id": "leaf", "component": "Text", "text": "hi"})
    assert len(chain_ids) == MAX_TREE_DEPTH
    assert validate_component_tree(components) == []


def test_depth_one_past_the_limit_is_rejected() -> None:
    from src.mcp.ui.catalog import MAX_TREE_DEPTH

    chain_ids = ["root"] + [f"n{i}" for i in range(1, MAX_TREE_DEPTH)] + ["leaf"]
    components = [
        {"id": chain_ids[i], "component": "Card", "child": chain_ids[i + 1]}
        for i in range(len(chain_ids) - 1)
    ]
    components.append({"id": "leaf", "component": "Text", "text": "hi"})
    assert len(chain_ids) == MAX_TREE_DEPTH + 1
    assert "DEPTH_EXCEEDED" in _codes(components)


def test_empty_tree_is_rejected() -> None:
    assert "EMPTY_TREE" in _codes([])


def test_dynamic_children_template_still_checks_its_component_id() -> None:
    """`children` may be a `{componentId, path}` template (`common_types.json#/ChildList`)
    for a data-model-driven list -- its `componentId` must still resolve.
    """
    components = [
        {
            "id": "root",
            "component": "Column",
            "children": {"componentId": "ghost", "path": "/items"},
        }
    ]
    assert "DANGLING_CHILD" in _codes(components)
