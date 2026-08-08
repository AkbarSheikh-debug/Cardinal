"""`providers.parse_provider` (D-056) -- pure string splitting, no network."""

from __future__ import annotations

import httpx
import pytest

from src.agent.providers import ProviderError, _retry_delay_s, parse_provider


def test_splits_simple_provider_model() -> None:
    assert parse_provider("groq/llama-3.3-70b-versatile") == ("groq", "llama-3.3-70b-versatile")


def test_splits_on_first_slash_only_for_nested_model_ids() -> None:
    assert parse_provider("openrouter/qwen/qwen3-32b") == ("openrouter", "qwen/qwen3-32b")


@pytest.mark.parametrize("bad_id", ["no-slash-here", "", "/missing-provider", "missing-model/"])
def test_rejects_malformed_ids(bad_id: str) -> None:
    with pytest.raises(ProviderError):
        parse_provider(bad_id)


def _response(headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(429, headers=headers or {}, request=httpx.Request("POST", "http://x"))


def test_retry_delay_honours_a_retry_after_header() -> None:
    assert _retry_delay_s(_response({"retry-after": "2.5"}), attempt=0) == 2.5


def test_retry_delay_falls_back_to_exponential_backoff_with_no_header() -> None:
    # D-064: Groq's own 429 names the wait in the JSON body's message text ("Please try again
    # in 855ms"), not a Retry-After header -- this fallback is what actually fires against it.
    assert _retry_delay_s(_response(), attempt=0) == 1.0
    assert _retry_delay_s(_response(), attempt=1) == 2.0
    assert _retry_delay_s(_response(), attempt=2) == 4.0


def test_retry_delay_falls_back_when_the_header_is_not_a_number() -> None:
    assert _retry_delay_s(_response({"retry-after": "not-a-number"}), attempt=0) == 1.0
