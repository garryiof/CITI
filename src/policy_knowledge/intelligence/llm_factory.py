"""Provider switch: mock | openai | guardrail."""

from __future__ import annotations

from typing import Any

from policy_knowledge.config import AppConfig, LLMConfig
from policy_knowledge.intelligence.guardrail_client import (
    LLMAdapter,
    create_guardrail_client,
)
from policy_knowledge.intelligence.openai_client import OpenAIAdapter
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM

SUPPORTED_PROVIDERS = frozenset({"mock", "synthetic", "openai", "guardrail"})


def normalize_provider(provider: str | None) -> str:
    value = (provider or "mock").strip().lower()
    if value in {"", "mock", "synthetic"}:
        return "mock"
    if value in {"openai", "guardrail"}:
        return value
    raise ValueError(
        f"Unsupported llm.provider={provider!r}. "
        f"Use one of: mock, openai, guardrail."
    )


def llm_runtime_status(llm: Any) -> dict[str, str]:
    """Honest connectivity labels for manifest / notebook prints."""
    name = type(llm).__name__
    if name in {"MockLLMAdapter", "SyntheticMockLLM"}:
        return {
            "llm_provider": "mock",
            "llm_status": "MOCK",
            "guardrail_status": "GUARDRAIL_NOT_CONNECTED",
        }
    if name == "OpenAIAdapter":
        return {
            "llm_provider": "openai",
            "llm_status": "OPENAI_CONNECTED",
            "guardrail_status": "GUARDRAIL_NOT_CONNECTED",
        }
    if name == "GuardRailClient":
        return {
            "llm_provider": "guardrail",
            "llm_status": "GUARDRAIL_CONNECTED",
            "guardrail_status": "CONNECTED",
        }
    return {
        "llm_provider": "unknown",
        "llm_status": "UNKNOWN",
        "guardrail_status": "UNKNOWN",
    }


def create_llm_client(
    config: AppConfig | LLMConfig | None = None,
    *,
    provider: str | None = None,
    require_live: bool = False,
    openai_client: Any | None = None,
) -> LLMAdapter:
    """
    Build the adapter selected by config/provider.

    - mock: SyntheticMockLLM (deterministic synthetic fixture path)
    - openai: OpenAIAdapter (home; needs openai package + OPENAI_API_KEY)
    - guardrail: create_guardrail_client (Hub; may raise if require_live)
    """
    llm_cfg: LLMConfig
    if config is None:
        llm_cfg = LLMConfig()
    elif isinstance(config, AppConfig):
        llm_cfg = config.llm
    else:
        llm_cfg = config

    chosen = normalize_provider(provider if provider is not None else llm_cfg.provider)

    if chosen == "mock":
        return SyntheticMockLLM()

    if chosen == "openai":
        return OpenAIAdapter.from_config(llm_cfg, client=openai_client)

    if chosen == "guardrail":
        return create_guardrail_client(require_live=require_live)

    raise ValueError(f"Unsupported provider after normalize: {chosen!r}")
