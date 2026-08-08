"""`interview_chat`'s pure parsing (D-056) -- the provider call itself is network, exercised
manually against Groq's free tier rather than in this suite (the same D-015 boundary every
other live-model path in this repo already lives behind).
"""

from __future__ import annotations

from src.agent.interview_chat import _parse_reply_and_updates, _strip_code_fence


def test_parses_reply_and_updates_from_well_formed_json() -> None:
    text = (
        '{"reply": "What is your budget?", "updates": '
        '[{"field": "goal", "value": "buy", "confidence": 0.9, "locked": true}]}'
    )
    reply, updates = _parse_reply_and_updates(text)
    assert reply == "What is your budget?"
    assert len(updates) == 1
    assert updates[0].field == "goal"
    assert updates[0].value == "buy"
    assert updates[0].confidence == 0.9
    assert updates[0].locked is True


def test_strips_markdown_code_fence_before_parsing() -> None:
    text = '```json\n{"reply": "ok", "updates": []}\n```'
    reply, updates = _parse_reply_and_updates(text)
    assert reply == "ok"
    assert updates == ()


def test_falls_back_to_raw_text_when_not_json() -> None:
    text = "Sure, tell me your budget."
    reply, updates = _parse_reply_and_updates(text)
    assert reply == text
    assert updates == ()


def test_falls_back_to_raw_text_when_json_is_not_an_object() -> None:
    text = "[1, 2, 3]"
    reply, updates = _parse_reply_and_updates(text)
    assert reply == text
    assert updates == ()


def test_missing_reply_falls_back_to_raw_text() -> None:
    text = '{"updates": [{"field": "budget", "value": {"amount": "1", "currency": "EUR"}}]}'
    reply, updates = _parse_reply_and_updates(text)
    assert reply == text
    assert len(updates) == 1


def test_updates_entries_missing_field_are_skipped() -> None:
    text = '{"reply": "ok", "updates": [{"value": "buy"}, {"field": "goal", "value": "buy"}]}'
    reply, updates = _parse_reply_and_updates(text)
    assert reply == "ok"
    assert len(updates) == 1
    assert updates[0].field == "goal"


def test_non_numeric_confidence_defaults_to_zero() -> None:
    text = '{"reply": "ok", "updates": [{"field": "goal", "value": "buy", "confidence": "n/a"}]}'
    _, updates = _parse_reply_and_updates(text)
    assert updates[0].confidence == 0.0


def test_strip_code_fence_leaves_plain_json_untouched() -> None:
    assert _strip_code_fence('{"a": 1}') == '{"a": 1}'


def test_strips_closed_think_block_before_parsing() -> None:
    text = '<think>the user wants a suv</think>{"reply": "ok", "updates": []}'
    reply, updates = _parse_reply_and_updates(text)
    assert reply == "ok"
    assert updates == ()


def test_unclosed_think_block_truncated_by_max_tokens_yields_empty_reply() -> None:
    # A reasoning model cut off mid-thought (max_tokens exhausted before the closing tag and
    # the JSON that would have followed it) -- verified live against groq/qwen/qwen3.6-27b.
    # The empty-reply fallback text lives in interview_turn, not in this pure parser.
    text = "<think>the user wants a suv, budget is 30000, let me structure the JSON respo"
    reply, updates = _parse_reply_and_updates(text)
    assert reply == ""
    assert updates == ()
