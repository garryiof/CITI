"""GuardRail adapter + MockLLMAdapter (discover live import; never invent paths)."""

from __future__ import annotations

import importlib
import json
import time
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class GuardRailUnavailable(RuntimeError):
    """Raised when a live GuardRail client is required but cannot be initialized."""


@runtime_checkable
class LLMAdapter(Protocol):
    def generate_text(self, messages: list[dict], **kwargs: Any) -> str: ...

    def generate_narrative(self, messages: list[dict], **kwargs: Any) -> str: ...

    def parse_structured(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel: ...


def build_messages(system: str, user: str) -> list[dict[str, str]]:
    """Thin local helper — swap if an organization helper appears."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _user_key(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return str(msg.get("content", ""))
    return ""


class MockLLMAdapter:
    """Deterministic mock for synthetic development — never claims live connectivity."""

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        structured_responses: dict[str, dict[str, Any]] | None = None,
        raw_structured_responses: dict[str, str] | None = None,
        fail_times_before_success: int = 0,
        default_text: str = "",
    ) -> None:
        self.responses = responses or {}
        self.structured_responses = structured_responses or {}
        self.raw_structured_responses = raw_structured_responses or {}
        self.fail_times_before_success = fail_times_before_success
        self.default_text = default_text
        self.attempt_count = 0
        self._fail_budget = fail_times_before_success

    def generate_text(self, messages: list[dict], **kwargs: Any) -> str:
        key = _user_key(messages)
        return self.responses.get(key, self.default_text)

    def generate_narrative(self, messages: list[dict], **kwargs: Any) -> str:
        return self.generate_text(messages, **kwargs)

    def parse_structured(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        max_retries = int(kwargs.get("max_retries", 0))
        key = _user_key(messages)
        attempts = 0
        last_error: Exception | None = None
        while True:
            attempts += 1
            self.attempt_count = attempts
            if self._fail_budget > 0:
                self._fail_budget -= 1
                last_error = RuntimeError("simulated transient failure")
                if attempts <= max_retries:
                    time.sleep(0)
                    continue
                raise last_error

            if key in self.raw_structured_responses:
                raw = self.raw_structured_responses[key]
                data = json.loads(raw)
                return schema.model_validate(data)

            if key in self.structured_responses:
                return schema.model_validate(self.structured_responses[key])

            raise KeyError(f"No mock structured response for user key: {key!r}")


class GuardRailClient:
    """Live wrapper — only constructed when GuardRail import discovery succeeds."""

    def __init__(self, backend: Any) -> None:
        self.backend = backend

    def generate_text(self, messages: list[dict], **kwargs: Any) -> str:
        raise GuardRailUnavailable(
            "Live GuardRail generate_text is not wired; discover org CREATE callable first."
        )

    def generate_narrative(self, messages: list[dict], **kwargs: Any) -> str:
        return self.generate_text(messages, **kwargs)

    def parse_structured(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        raise GuardRailUnavailable(
            "Live GuardRail parse_structured is not wired; discover org PARSE callable first."
        )


def discover_guardrail_module() -> Any | None:
    """Attempt known-safe discovery only — do not invent package paths beyond these probes."""
    candidates = [
        "guardrail",
        "GuardRail",
        "citi_guardrail",
        "guardrail_client",
    ]
    for name in candidates:
        try:
            return importlib.import_module(name)
        except ImportError:
            continue
    return None


def create_guardrail_client(*, require_live: bool = False, soeid: str | None = None) -> LLMAdapter:
    """
    Return a live GuardRailClient when the module is discoverable; otherwise Mock.

    If require_live=True and GuardRail cannot be imported/initialized, raise GuardRailUnavailable.
    """
    mod = discover_guardrail_module()
    if mod is None:
        if require_live:
            raise GuardRailUnavailable(
                "GUARDRAIL_NOT_CONNECTED: GuardRail module not found. "
                "Use MockLLMAdapter for synthetic runs; see docs/guardrail_integration.md."
            )
        return MockLLMAdapter()

    # Module present but initialize/generate contracts are org-specific — do not invent them.
    if require_live:
        raise GuardRailUnavailable(
            "GUARDRAIL_NOT_CONNECTED: GuardRail module imported but CREATE/PARSE "
            "wiring is not configured in this POC scaffold. Complete docs/guardrail_integration.md."
        )
    return MockLLMAdapter()
