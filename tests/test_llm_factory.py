"""Provider factory: mock | openai | guardrail."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from policy_knowledge.config import AppConfig, LLMConfig
from policy_knowledge.intelligence.llm_factory import (
    create_llm_client,
    llm_runtime_status,
    normalize_provider,
)
from policy_knowledge.intelligence.openai_client import OpenAIAdapter, OpenAIUnavailable
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM


class TinySchema(BaseModel):
    name: str
    count: int = Field(ge=0)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class FakeOpenAIClient:
    def __init__(self, content: str = '{"name":"from-openai","count":3}') -> None:
        self.content = content
        self.calls: list[dict] = []

        class Completions:
            def __init__(self, outer: "FakeOpenAIClient") -> None:
                self._outer = outer

            def create(self, **kwargs):
                self._outer.calls.append(kwargs)
                return _FakeResponse(self._outer.content)

        class Chat:
            def __init__(self, outer: "FakeOpenAIClient") -> None:
                self.completions = Completions(outer)

        self.chat = Chat(self)


def test_normalize_provider_aliases():
    assert normalize_provider("MOCK") == "mock"
    assert normalize_provider("synthetic") == "mock"
    assert normalize_provider("openai") == "openai"
    assert normalize_provider("guardrail") == "guardrail"
    with pytest.raises(ValueError):
        normalize_provider("anthropic")


def test_create_mock_from_config():
    cfg = AppConfig(llm=LLMConfig(provider="mock"))
    llm = create_llm_client(cfg)
    assert isinstance(llm, SyntheticMockLLM)
    status = llm_runtime_status(llm)
    assert status["llm_provider"] == "mock"
    assert status["guardrail_status"] == "GUARDRAIL_NOT_CONNECTED"


def test_create_openai_with_injected_client(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fake = FakeOpenAIClient()
    cfg = LLMConfig(provider="openai", model="gpt-4o-mini", max_retries=0)
    llm = create_llm_client(cfg, openai_client=fake)
    assert isinstance(llm, OpenAIAdapter)
    result = llm.parse_structured(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "go"}],
        TinySchema,
        max_retries=0,
    )
    assert result.name == "from-openai"
    assert result.count == 3
    assert fake.calls
    assert fake.calls[0]["response_format"] == {"type": "json_object"}
    assert llm_runtime_status(llm)["llm_status"] == "OPENAI_CONNECTED"


def test_openai_requires_api_key_without_client(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(OpenAIUnavailable):
        OpenAIAdapter(model="gpt-4o-mini")


def test_create_guardrail_falls_back_or_raises():
    from policy_knowledge.intelligence.guardrail_client import GuardRailUnavailable

    with pytest.raises(GuardRailUnavailable):
        create_llm_client(LLMConfig(provider="guardrail"), require_live=True)

    llm = create_llm_client(LLMConfig(provider="guardrail"), require_live=False)
    # Scaffold returns MockLLMAdapter when GuardRail is not wired.
    assert type(llm).__name__ in {"MockLLMAdapter", "SyntheticMockLLM", "GuardRailClient"}


def test_openai_generate_text_uses_fake_client():
    fake = FakeOpenAIClient(content="hello narrative")
    adapter = OpenAIAdapter(api_key="sk-test", client=fake, max_retries=0)
    text = adapter.generate_text([{"role": "user", "content": "hi"}])
    assert text == "hello narrative"
    assert llm_runtime_status(adapter)["llm_provider"] == "openai"


def test_env_provider_override(monkeypatch, tmp_path):
    cfg_path = tmp_path / "app.yaml"
    cfg_path.write_text("llm:\n  provider: mock\n", encoding="utf-8")
    monkeypatch.setenv("POLICY_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from policy_knowledge.config import load_config

    loaded = load_config(cfg_path)
    assert loaded.llm.provider == "openai"
