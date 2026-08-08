"""Provider-agnostic chat completions for the INTERVIEW phase's model-selectable path
(D-056). Deliberately scoped to one plain, non-tool chat call: RESEARCH and everything after
it keeps running through `CardinalOrchestrator`'s Claude Agent SDK session, tools and
guardrails untouched -- CONSTITUTION I.2's `confirm_booking` invisibility is a property of
that session's `mcp_servers` construction (PHASE-2 gate 2.6), not something this module
touches or needs to reimplement.

Four providers, three of them (`groq`, `openrouter`, `openai`) sharing one OpenAI-compatible
`/chat/completions` shape and differing only in base URL and API key -- `google` (Gemini) has
its own REST shape and gets its own function. Plain `httpx` rather than each provider's SDK:
this module is one call, not a client library, and `httpx` is already a transitive dependency
(FastAPI's own test client pulls it in) rather than a new one to add.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

_TIMEOUT_S = 60.0

#: Groq's free tier caps tokens-per-minute per model (8000 for a reasoning model is easy to
#: hit with one 2000-max_tokens request, D-058's headroom for <think>) -- verified live
#: (D-064): a 429 there names the wait itself ("Please try again in 855ms"), which is what
#: makes it worth one bounded retry instead of surfacing a raw provider error straight into
#: the chat rail mid-demo. Capped at 3 attempts / ~7s worst case added latency so a real outage
#: still fails loudly rather than stalling a live turn silently.
_MAX_RATE_LIMIT_RETRIES: int = 3
_RETRY_BASE_DELAY_S: float = 1.0


class ProviderError(RuntimeError):
    """A provider call failed -- missing key, HTTP error, or an unparseable response body."""


def parse_provider(model_id: str) -> tuple[str, str]:
    """`"groq/llama-3.3-70b-versatile"` -> `("groq", "llama-3.3-70b-versatile")`. Splits on
    the *first* `/` only, since an OpenRouter model id is itself `org/model` (PHASE-3-adjacent:
    `"openrouter/qwen/qwen3-32b"` -> `("openrouter", "qwen/qwen3-32b")`).
    """
    provider, _, model = model_id.partition("/")
    if not provider or not model:
        raise ProviderError(f"invalid model id {model_id!r}, expected 'provider/model'")
    return provider, model


_OPENAI_COMPATIBLE: dict[str, tuple[str, str]] = {
    # provider -> (base_url, api_key env var)
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
}


def _require_key(env_var: str) -> str:
    key = os.environ.get(env_var, "").strip()
    if not key:
        raise ProviderError(f"{env_var} is not set")
    return key


#: Providers whose `/chat/completions` accepts Groq's `reasoning_format` key. Sending it to
#: one that doesn't is a 400, so this is an allowlist rather than a pass-through -- OpenRouter
#: spells the same idea `reasoning: {exclude: true}` and OpenAI has no equivalent at all.
_SUPPORTS_REASONING_FORMAT = frozenset({"groq"})


def _retry_delay_s(resp: httpx.Response, attempt: int) -> float:
    """A standard `Retry-After` header wins when a provider sends one; otherwise a short
    exponential backoff (1s, 2s, 4s) -- Groq's own 429 body names its wait in prose
    ("Please try again in 855ms") rather than a header, so the fallback is what actually
    fires against it today, verified live (D-064).
    """
    header = resp.headers.get("retry-after")
    fallback: float = _RETRY_BASE_DELAY_S * (2.0**attempt)
    if header is None:
        return fallback
    try:
        return max(0.1, float(str(header)))
    except ValueError:
        return fallback


async def _openai_compatible_chat(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    reasoning_format: str | None = None,
) -> str:
    base_url, env_var = _OPENAI_COMPATIBLE[provider]
    api_key = _require_key(env_var)
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if reasoning_format and provider in _SUPPORTS_REASONING_FORMAT:
        body["reasoning_format"] = reasoning_format
    async with httpx.AsyncClient(base_url=base_url, timeout=_TIMEOUT_S) as client:
        for attempt in range(_MAX_RATE_LIMIT_RETRIES + 1):
            resp = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            )
            if resp.status_code != 429 or attempt == _MAX_RATE_LIMIT_RETRIES:
                break
            await asyncio.sleep(_retry_delay_s(resp, attempt))
    if resp.status_code != 200:
        raise ProviderError(
            f"{provider} chat completion failed: {resp.status_code} {resp.text[:300]}"
        )
    body = resp.json()
    try:
        return body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"{provider} returned an unexpected response shape") from exc


async def _gemini_chat(
    model: str, messages: list[dict[str, str]], *, temperature: float, max_tokens: int
) -> str:
    api_key = _require_key("GEMINI_API_KEY")
    # Gemini's REST `contents` has no "system" role -- fold any system message(s) into the
    # separate `systemInstruction` field instead, and rename "assistant" to Gemini's "model".
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] != "system"
    ]
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        resp = await client.post(url, params={"key": api_key}, json=payload)
    if resp.status_code != 200:
        raise ProviderError(f"google chat completion failed: {resp.status_code} {resp.text[:300]}")
    body = resp.json()
    try:
        parts = body["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("google returned an unexpected response shape") from exc


async def _anthropic_chat(
    model: str, messages: list[dict[str, str]], *, temperature: float, max_tokens: int
) -> str:
    # Only reachable if the model catalog ever offers a bare "anthropic/..." id through this
    # path -- today the catalog's Claude entry is handled upstream (interview_chat.py routes
    # it through CardinalOrchestrator instead, the same live session RESEARCH onward uses).
    # Kept for completeness/symmetry rather than left to raise "unknown provider".
    api_key = _require_key("ANTHROPIC_API_KEY")
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    turns = [m for m in messages if m["role"] != "system"]
    payload: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": turns}
    if temperature is not None:
        payload["temperature"] = temperature
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
    if resp.status_code != 200:
        raise ProviderError(
            f"anthropic chat completion failed: {resp.status_code} {resp.text[:300]}"
        )
    body = resp.json()
    try:
        return "".join(block["text"] for block in body["content"] if block.get("type") == "text")
    except (KeyError, TypeError) as exc:
        raise ProviderError("anthropic returned an unexpected response shape") from exc


async def chat(
    model_id: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.4,
    max_tokens: int = 700,
    reasoning_format: str | None = None,
) -> str:
    """One chat completion, routed by `model_id`'s `provider/model` prefix. `messages` is the
    plain OpenAI-shaped `[{"role": "system"|"user"|"assistant", "content": str}, ...]` --
    every provider function above adapts it to that provider's own wire shape.

    `reasoning_format="hidden"` asks a reasoning model to keep its chain of thought out of
    `content` entirely, so a caller parsing structured output never has to strip a `<think>`
    block and never loses the answer to one that ran past `max_tokens` (D-058). Silently
    ignored by providers that don't support the key -- it is an optimisation, not a contract,
    and every caller must still tolerate a `<think>` block arriving anyway.
    """
    provider, model = parse_provider(model_id)
    if provider in _OPENAI_COMPATIBLE:
        return await _openai_compatible_chat(
            provider,
            model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_format=reasoning_format,
        )
    if provider == "google":
        return await _gemini_chat(model, messages, temperature=temperature, max_tokens=max_tokens)
    if provider == "anthropic":
        return await _anthropic_chat(
            model, messages, temperature=temperature, max_tokens=max_tokens
        )
    raise ProviderError(f"unknown provider {provider!r} in model id {model_id!r}")
