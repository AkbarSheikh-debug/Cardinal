"""The INTERVIEW-phase model picker's catalog (D-056) -- exposed to the frontend via
`GET /models` so the chat rail can render the same kind of picker `D:\\Interview Agent`'s
`model_catalog.py` does. Model ids are `provider/model`, parsed by `providers.parse_provider`.

Free-tier Groq entries are listed first and marked `default=True` on the recommended one --
`docker compose up`'s zero-config path is still Claude via `CardinalOrchestrator` (nothing
here changes unless a session explicitly calls `POST /sessions/{id}/model`), but Groq is
what a developer testing this feature should reach for: no cost, no credit card, and it is
what this catalog was verified against (D-056).
"""

from __future__ import annotations

import os
from typing import TypedDict


class ModelInfo(TypedDict):
    id: str
    label: str
    provider: str
    free: bool
    reasoning: bool
    description: str


CLAUDE_MODEL_ID = "claude"
"""Not a `provider/model` id -- the sentinel meaning "don't use `providers.chat` at all, run
this session through `CardinalOrchestrator` from the first turn," i.e. today's only behaviour
before this feature existed. `parse_provider` never sees this value (`interview_chat`'s caller
branches on it first)."""

MODELS: tuple[ModelInfo, ...] = (
    {
        "id": CLAUDE_MODEL_ID,
        "label": "Claude (default)",
        "provider": "anthropic",
        "free": False,
        "reasoning": False,
        "description": "Cardinal's own model, unchanged. Runs the full agentic session -- "
        "interview, search, ranking and booking -- through the Claude Agent SDK end to end.",
    },
    {
        "id": "groq/llama-3.3-70b-versatile",
        "label": "Llama 3.3 70B (Groq)",
        "provider": "groq",
        "free": True,
        "reasoning": False,
        "description": "Meta's flagship open chat model on Groq's LPU inference. Fast, free.",
    },
    {
        "id": "groq/qwen/qwen3.6-27b",
        "label": "Qwen 3.6 27B (Groq)",
        "provider": "groq",
        "free": True,
        "reasoning": True,
        "description": "Alibaba's reasoning model. Strong on structured extraction. Free on Groq.",
    },
    {
        "id": "groq/openai/gpt-oss-120b",
        "label": "GPT-OSS 120B (Groq)",
        "provider": "groq",
        "free": True,
        "reasoning": False,
        "description": "OpenAI's open-weight 120B model, served on Groq. Free.",
    },
    {
        "id": "google/gemini-2.5-flash",
        "label": "Gemini 2.5 Flash",
        "provider": "google",
        "free": True,
        "reasoning": False,
        "description": "Google's fast Gemini variant. Free tier via AI Studio.",
    },
    {
        "id": "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        "label": "Nemotron 3 Super 120B (OpenRouter)",
        "provider": "openrouter",
        "free": True,
        "reasoning": True,
        "description": "NVIDIA's reasoning model, via OpenRouter's free tier.",
    },
    {
        "id": "openai/gpt-4o",
        "label": "GPT-4o (paid)",
        "provider": "openai",
        "free": False,
        "reasoning": False,
        "description": "Requires a paid OpenAI API key.",
    },
)


def find(model_id: str) -> ModelInfo | None:
    return next((m for m in MODELS if m["id"] == model_id), None)


# ---------------------------------------------------------------------------
# What the product actually runs on, and what it admits to (D-059)
# ---------------------------------------------------------------------------

FALLBACK_INTERVIEW_MODEL_ID = "groq/qwen/qwen3.6-27b"
"""The INTERVIEW phase's default when nothing overrides it. Which model asks the interview
questions is an implementation detail of the product, not a user-facing choice -- the picker
was a developer affordance (D-056) and it is off by default now (`show_picker`).

Overridable with `CARDINAL_INTERVIEW_MODEL` so this stays a config decision rather than a
code one; set it to `"claude"` to put the whole session back on `CardinalOrchestrator` from
the first turn, which is what every phase gate still assumes.
"""


def default_interview_model_id() -> str:
    """Resolved per call rather than at import, so a test or a `docker compose` env change
    takes effect without reimporting the module. Falls back to `CLAUDE_MODEL_ID` when the
    configured default names a model this catalog doesn't carry -- an unroutable id would
    otherwise 502 every first turn with no way for the user to pick their way out, since
    the picker they'd use is hidden.
    """
    configured = os.environ.get("CARDINAL_INTERVIEW_MODEL", "").strip()
    if not configured:
        configured = FALLBACK_INTERVIEW_MODEL_ID
    if configured == CLAUDE_MODEL_ID or find(configured):
        return configured
    return CLAUDE_MODEL_ID


def show_picker() -> bool:
    """`CARDINAL_SHOW_MODEL_PICKER=true` restores D-056's developer picker. Off by default:
    a demo viewer seeing a list of third-party model names learns something about Cardinal's
    internals that is neither true of the product (search, ranking and booking are Claude's
    either way) nor useful to them.
    """
    return os.environ.get("CARDINAL_SHOW_MODEL_PICKER", "").strip().lower() in {"1", "true", "yes"}


def visible_models() -> tuple[ModelInfo, ...]:
    """What `GET /models` serves. Empty unless the picker is switched on -- `web/`'s rail
    renders no picker for a list this short, so hiding it needs no frontend branch.
    """
    return MODELS if show_picker() else ()
