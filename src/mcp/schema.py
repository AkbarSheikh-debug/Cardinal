"""One helper, used by every tool's `input_schema` (PHASE-2 §5).

`strict_schema` exists so "every input schema sets `additionalProperties: false` and
`strict: true`" (gate 2.3) is true by construction rather than by fourteen people remembering
to type the same two keys. `create_sdk_mcp_server` accepts a raw JSON Schema dict as long as
it carries `type` and `properties` (see `claude_agent_sdk.__init__._build_schema`), which is
exactly what this returns.
"""

from __future__ import annotations

from typing import Any


def strict_schema(
    properties: dict[str, dict[str, Any]], *, required: list[str] | None = None
) -> dict[str, Any]:
    """A tool input schema that rejects unknown fields and declares itself strict.

    `required` defaults to every property -- optional parameters must say so explicitly by
    passing a narrower list, so an omission is a choice, not an oversight.
    """
    return {
        "type": "object",
        "properties": properties,
        "required": required if required is not None else list(properties.keys()),
        "additionalProperties": False,
        "strict": True,
    }


def enum_property(values: tuple[str, ...], *, description: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(values), "description": description}


def enum_array_property(values: tuple[str, ...], *, description: str) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "string", "enum": list(values)},
        "description": description,
    }
