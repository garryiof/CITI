"""Provider factory: mock | guardrail | llama4 (CITI_ONLY — no OpenAI)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from policy_knowledge.config import AppConfig, LLMConfig
from policy_knowledge.intelligence.llm_factory import (
    create_llm_client,
    llm_runtime_status,
    normalize_provider,
)
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM


class TinySchema(BaseModel):
    name: str
    count: int = Field(ge=0)


def test_normalize_provider_aliases():
    assert normalize_provider("MOCK") == "mock"
    assert normalize_provider("synthetic") == "mock"
    assert normalize_provider("guardrail") == "guardrail"
    assert normalize_provider("llama4") == "guardrail"
    assert normalize_provider("llama-4") == "guardrail"
    with pytest.raises(ValueError):
        normalize_provider("openai")
    with pytest.raises(ValueError):
        normalize_provider("anthropic")


def test_create_mock_from_config():
    cfg = AppConfig(llm=LLMConfig(provider="mock"))
    llm = create_llm_client(cfg)
    assert isinstance(llm, SyntheticMockLLM)
    status = llm_runtime_status(llm)
    assert status["llm_provider"] == "mock"
    assert status["guardrail_status"] == "GUARDRAIL_NOT_CONNECTED"


def test_create_guardrail_falls_back_or_raises():
    from policy_knowledge.intelligence.guardrail_client import GuardRailUnavailable

    with pytest.raises(GuardRailUnavailable):
        create_llm_client(LLMConfig(provider="guardrail"), require_live=True)

    llm = create_llm_client(LLMConfig(provider="guardrail"), require_live=False)
    # Without a Hub GuardRail module, factory returns MockLLMAdapter.
    assert type(llm).__name__ in {"MockLLMAdapter", "SyntheticMockLLM", "GuardRailClient"}


def test_llama4_alias_uses_guardrail_client_when_backend_injected(monkeypatch):
    from policy_knowledge.intelligence import guardrail_client as gr

    class _Msg:
        def __init__(self, content: str) -> None:
            self.content = content

    class _Choice:
        def __init__(self, content: str) -> None:
            self.message = _Msg(content)

    class _Completion:
        def __init__(self, content: str) -> None:
            self.choices = [_Choice(content)]

    class FakeGuardRail:
        INITIALIZED = False

        @staticmethod
        def INITIALIZE(soeid: str) -> None:
            FakeGuardRail.INITIALIZED = True

        @staticmethod
        def CHAT_COMPLETIONS_CREATE(**kwargs):
            assert kwargs["model"] == "Llama-4-Scout-17B-16E-Instruct"
            # Hub returns (request_id, completion)
            return ("req-1", _Completion('{"name":"llama","count":1}'))

        @staticmethod
        def CHAT_COMPLETIONS_PARSE(**kwargs):
            return ("req-2", _Completion('{"name":"llama","count":1}'))

    monkeypatch.setenv("SOEID", "TESTSOE")
    llm = gr.create_guardrail_client(
        require_live=True,
        model="Llama-4-Scout-17B-16E-Instruct",
        backend=FakeGuardRail,
        max_retries=0,
    )
    assert type(llm).__name__ == "GuardRailClient"
    assert FakeGuardRail.INITIALIZED is True
    assert llm.generate_text([{"role": "user", "content": "x"}]).startswith("{")
    result = llm.parse_structured(
        [{"role": "user", "content": "go"}],
        TinySchema,
        max_retries=0,
    )
    assert result.name == "llama"
    status = llm_runtime_status(llm)
    assert status["llm_status"] == "GUARDRAIL_CONNECTED"
    assert status["llm_model"] == "Llama-4-Scout-17B-16E-Instruct"


def test_create_llm_client_llama4_provider():
    llm = create_llm_client(LLMConfig(provider="llama4", model="Llama-4-Scout"), require_live=False)
    assert type(llm).__name__ in {"MockLLMAdapter", "SyntheticMockLLM", "GuardRailClient"}


def test_discover_prefers_guardrail_last_class(monkeypatch):
    from policy_knowledge.intelligence import guardrail_client as gr

    class FakeGuardRail:
        @staticmethod
        def CHAT_COMPLETIONS_CREATE(**kwargs):
            return ("id", type("C", (), {"choices": []})())

    import sys
    import types

    mod = types.ModuleType("guardrail_last")
    mod.GuardRail = FakeGuardRail  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "guardrail_last", mod)

    discovered = gr.discover_guardrail_module()
    assert discovered is FakeGuardRail


def test_env_provider_override(monkeypatch, tmp_path):
    cfg_path = tmp_path / "app.yaml"
    cfg_path.write_text("llm:\n  provider: mock\n", encoding="utf-8")
    monkeypatch.setenv("POLICY_LLM_PROVIDER", "llama4")
    from policy_knowledge.config import load_config

    loaded = load_config(cfg_path)
    assert loaded.llm.provider == "llama4"
