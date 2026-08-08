"""The A2UI v0.9 wire protocol (PHASE-6 SS4/SS6), built directly from the protocol's own
published schema (`@a2ui/web_core/v0_9`'s `schemas/server_to_client.json`) rather than
guessed at -- every message this module builds is shaped to validate against that schema
character for character: `version` is the literal `"v0.9"`, and each message wraps exactly
one of `createSurface` / `updateComponents` / `updateDataModel` / `deleteSurface`.

Plain functions returning `dict`, not a wrapper class: these are only ever serialised to JSON
and pushed down the SSE transport (`src/api`, PHASE-6 SS6) or handed to a test as a fixture.
A class here would buy nothing a dict doesn't already have and cost a second representation to
keep in sync with the schema.
"""

from __future__ import annotations

from typing import Any

PROTOCOL_VERSION = "v0.9"

ComponentDict = dict[str, Any]
Message = dict[str, Any]


def create_surface_message(
    surface_id: str, *, catalog_id: str, theme: dict[str, Any] | None = None
) -> Message:
    payload: dict[str, Any] = {"surfaceId": surface_id, "catalogId": catalog_id}
    if theme is not None:
        payload["theme"] = theme
    return {"version": PROTOCOL_VERSION, "createSurface": payload}


def update_components_message(surface_id: str, components: list[ComponentDict]) -> Message:
    if not components:
        raise ValueError("updateComponents requires at least one component")
    return {
        "version": PROTOCOL_VERSION,
        "updateComponents": {"surfaceId": surface_id, "components": components},
    }


def update_data_model_message(surface_id: str, value: Any, *, path: str = "/") -> Message:
    return {
        "version": PROTOCOL_VERSION,
        "updateDataModel": {"surfaceId": surface_id, "path": path, "value": value},
    }


def delete_surface_message(surface_id: str) -> Message:
    return {"version": PROTOCOL_VERSION, "deleteSurface": {"surfaceId": surface_id}}


def component(
    component_id: str,
    component_type: str,
    props: dict[str, Any] | None = None,
) -> ComponentDict:
    """One entry in an `updateComponents` message's `components` array.

    `id` and `component` are the two keys the protocol's discriminator relies on
    (`catalog.json#/$defs/anyComponent`, `discriminator: {propertyName: "component"}");
    everything else is the component's own props, spread flat alongside them -- exactly the
    shape `basic_catalog.json`'s per-component schemas declare (e.g. `Card`'s `child`, `Text`'s
    `text`), not nested under a `props` key.
    """
    return {"id": component_id, "component": component_type, **(props or {})}
