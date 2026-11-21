"""Mock LLM adapter / GuardRail client behavior."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, Field

from policy_knowledge.intelligence.guardrail_client import (
    GuardRailUnavailable,
    MockLLMAdapter,
    build_messages,
    create_guardrail_client,
)


class TinySchema(BaseModel):
    name: str
    count: int = Field(ge=0)


def test_build_messages_formats_system_and_user():
    msgs = build_messages("sys", "user text")
    assert msgs == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user text"},
    ]


def test_mock_generate_text_and_narrative():
    mock = MockLLMAdapter(responses={"hello": "world", "narrate": "Once upon a policy"})
    assert mock.generate_text(build_messages("s", "hello")) == "world"
    assert mock.generate_narrative(build_messages("s", "narrate")).startswith("Once")


def test_mock_parse_structured_happy_path():
    payload = {"name": "alpha", "count": 2}
    mock = MockLLMAdapter(structured_responses={"parse-me": payload})
    result = mock.parse_structured(build_messages("s", "parse-me"), TinySchema)
    assert isinstance(result, TinySchema)
    assert result.name == "alpha"
    assert result.count == 2


def test_mock_parse_malformed_json_raises():
    mock = MockLLMAdapter(raw_structured_responses={"bad": "{not-json"})
    with pytest.raises(json.JSONDecodeError):
        mock.parse_structured(build_messages("s", "bad"), TinySchema)


def test_mock_retry_then_success():
    mock = MockLLMAdapter(
        structured_responses={"retry": {"name": "ok", "count": 1}},
        fail_times_before_success=2,
    )
    result = mock.parse_structured(
        build_messages("s", "retry"),
        TinySchema,
        max_retries=3,
    )
    assert result.name == "ok"
    assert mock.attempt_count == 3


def test_live_guardrail_unavailable_without_import():
    with pytest.raises(GuardRailUnavailable):
        create_guardrail_client(require_live=True)
