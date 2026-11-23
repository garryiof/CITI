"""Provider switch: mock | guardrail | llama4 (alias → guardrail). CITI Hub only."""

from __future__ import annotations

from typing import Any, Optional, Union

from policy_knowledge.config import AppConfig, LLMConfig
from policy_knowledge.intelligence.guardrail_client import (
    LLMAdapter,
    create_guardrail_client,
)
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM

SUPPORTED_PROVIDERS = frozenset(
    {"mock", "synthetic", "guardrail", "llama4", "llama-4", "llama"}
)


def normalize_provider(provider: Optional[str]) -> str:
    value = (provider or "mock").strip().lower()
    if value in {"", "mock", "synthetic"}:
        return "mock"
    # CITI Hub: Llama 4 (and peers) are served through GuardRail.
    if value in {"guardrail", "llama4", "llama-4", "llama"}:
        return "guardrail"
    raise ValueError(
        f"Unsupported llm.provider={provider!r}. "
        f"Use one of: mock, guardrail, llama4."
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
    if name == "GuardRailClient":
        model = getattr(llm, "model", "") or ""
        return {
            "llm_provider": "guardrail",
            "llm_status": "GUARDRAIL_CONNECTED",
            "guardrail_status": "CONNECTED",
            "llm_model": str(model),
        }
    return {
        "llm_provider": "unknown",
        "llm_status": "UNKNOWN",
        "guardrail_status": "UNKNOWN",
    }


def create_llm_client(
    config: Optional[Union[AppConfig, LLMConfig]] = None,
    *,
    provider: Optional[str] = None,
    require_live: bool = False,
) -> LLMAdapter:
    """
    Build the adapter selected by config/provider.

    - mock: SyntheticMockLLM (deterministic synthetic fixture path)
    - guardrail / llama4: create_guardrail_client (CITI Hub; Llama 4 via MODEL)
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

    if chosen == "guardrail":
        return create_guardrail_client(
            require_live=require_live,
            model=getattr(llm_cfg, "model", None),
            narrative_model=getattr(llm_cfg, "narrative_model", None),
            temperature=float(getattr(llm_cfg, "temperature", 0.0) or 0.0),
            max_retries=int(getattr(llm_cfg, "max_retries", 3) or 3),
            extra_body=dict(getattr(llm_cfg, "extra_body", None) or {}),
            parse_extra_body=dict(getattr(llm_cfg, "parse_extra_body", None) or {}),
            n=int(getattr(llm_cfg, "n", 1) or 1),
        )

    raise ValueError(f"Unsupported provider after normalize: {chosen!r}")
