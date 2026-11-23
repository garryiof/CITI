"""GuardRail adapter + MockLLMAdapter (discover live import; never invent paths)."""

from __future__ import annotations

import importlib
import json
import os
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


def _schema_hint(schema: type[BaseModel]) -> str:
    try:
        payload = schema.model_json_schema()
    except Exception:
        payload = {"title": schema.__name__}
    schema_json = json.dumps(payload, ensure_ascii=False)
    try:
        from policy_knowledge.intelligence.prompt_loader import load_prompt

        return load_prompt(
            "schema_json_object",
            variables={"schema_json": schema_json},
        ).text
    except Exception:
        return (
            "Respond with a single JSON object that validates against this schema. "
            "Do not wrap in markdown.\n"
            f"{schema_json}"
        )


def _completion_text(completion: Any) -> str:
    """Best-effort extract text from GuardRail-shaped completions."""
    if completion is None:
        return ""
    if isinstance(completion, str):
        return completion
    choices = getattr(completion, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None) if message is not None else None
        if content:
            return str(content)
        text = getattr(choices[0], "text", None)
        if text:
            return str(text)
    if isinstance(completion, dict):
        choices = completion.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            if msg.get("content"):
                return str(msg["content"])
            if choices[0].get("text"):
                return str(choices[0]["text"])
    dump = getattr(completion, "model_dump", None)
    if callable(dump):
        return _completion_text(dump())
    raise RuntimeError(f"Unrecognized GuardRail completion shape: {type(completion)!r}")


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
    """Live wrapper around org GuardRail CREATE/PARSE (Llama 4 etc. via model=)."""

    def __init__(
        self,
        backend: Any,
        *,
        model: str,
        narrative_model: str | None = None,
        soeid: str | None = None,
        temperature: float = 0.0,
        max_retries: int = 3,
        extra_body: dict[str, Any] | None = None,
        parse_extra_body: dict[str, Any] | None = None,
        n: int = 1,
    ) -> None:
        self.backend = backend
        self.model = model
        self.narrative_model = narrative_model or model
        self.soeid = soeid or os.environ.get("SOEID") or os.environ.get("POLICY_SOEID")
        self.temperature = temperature
        self.max_retries = max_retries
        self.extra_body = dict(extra_body or {})
        self.parse_extra_body = dict(parse_extra_body or {})
        self.n = n
        self._initialize()

    def _initialize(self) -> None:
        init = getattr(self.backend, "INITIALIZE", None)
        if callable(init) and self.soeid:
            try:
                init(self.soeid)
            except Exception as exc:  # noqa: BLE001
                raise GuardRailUnavailable(
                    f"GUARDRAIL_NOT_CONNECTED: INITIALIZE failed: {exc}"
                ) from exc

    def _create_callable(self) -> Any:
        create = getattr(self.backend, "CHAT_COMPLETIONS_CREATE", None)
        if not callable(create):
            raise GuardRailUnavailable(
                "GUARDRAIL_NOT_CONNECTED: CHAT_COMPLETIONS_CREATE not found on GuardRail module."
            )
        return create

    def _parse_callable(self) -> Any | None:
        parse = getattr(self.backend, "CHAT_COMPLETIONS_PARSE", None)
        return parse if callable(parse) else None

    def _invoke_create(
        self,
        messages: list[dict],
        *,
        model: str,
        extra_body: dict[str, Any] | None = None,
    ) -> str:
        create = self._create_callable()
        kwargs: dict[str, Any] = {
            "messages": messages,
            "model": model,
            "n": self.n,
            "temperature": self.temperature,
        }
        if self.soeid:
            kwargs["user"] = self.soeid
        body = dict(self.extra_body)
        if extra_body:
            body.update(extra_body)
        if body:
            kwargs["extra_body"] = body
        completion = create(**kwargs)
        text = _completion_text(completion)
        if not text:
            raise RuntimeError("GuardRail CREATE returned empty content")
        return text

    def generate_text(self, messages: list[dict], **kwargs: Any) -> str:
        model = str(kwargs.get("model") or self.model)
        return self._invoke_create(messages, model=model)

    def generate_narrative(self, messages: list[dict], **kwargs: Any) -> str:
        model = str(kwargs.get("model") or self.narrative_model)
        return self._invoke_create(messages, model=model)

    def parse_structured(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        max_retries = int(kwargs.get("max_retries", self.max_retries))
        model = str(kwargs.get("model") or self.model)
        enriched = list(messages)
        if enriched and enriched[0].get("role") == "system":
            enriched[0] = {
                **enriched[0],
                "content": f"{enriched[0].get('content', '')}\n\n{_schema_hint(schema)}",
            }
        else:
            enriched = [{"role": "system", "content": _schema_hint(schema)}, *enriched]

        parse = self._parse_callable()
        last_error: Exception | None = None
        attempts = 0
        while attempts <= max_retries:
            attempts += 1
            try:
                if parse is not None:
                    parse_kwargs: dict[str, Any] = {
                        "messages": enriched,
                        "model": model,
                    }
                    if self.soeid:
                        parse_kwargs["user"] = self.soeid
                    body = dict(self.parse_extra_body)
                    if body:
                        parse_kwargs["extra_body"] = body
                    # Prefer response_format / schema kwargs when supported by org wrapper.
                    if "response_format" not in parse_kwargs:
                        try:
                            parse_kwargs["response_format"] = schema
                        except Exception:
                            pass
                    completion = parse(**parse_kwargs)
                    raw = _completion_text(completion)
                else:
                    raw = self._invoke_create(
                        enriched,
                        model=model,
                        extra_body={"response_format": {"type": "json_object"}},
                    )
                data = json.loads(raw)
                return schema.model_validate(data)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempts <= max_retries:
                    time.sleep(min(0.5 * attempts, 2.0))
                    continue
                raise
        assert last_error is not None
        raise last_error


def discover_guardrail_module() -> Any | None:
    """Attempt known-safe discovery only — do not invent package paths beyond these probes."""
    candidates = [
        "guardrail_last",  # CITI Hub module name
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


def create_guardrail_client(
    *,
    require_live: bool = False,
    soeid: str | None = None,
    model: str | None = None,
    narrative_model: str | None = None,
    temperature: float = 0.0,
    max_retries: int = 3,
    extra_body: dict[str, Any] | None = None,
    parse_extra_body: dict[str, Any] | None = None,
    n: int = 1,
    backend: Any | None = None,
) -> LLMAdapter:
    """
    Return a live GuardRailClient when the module exposes CREATE; otherwise Mock.

    Model defaults to Llama 4 Scout label when unset — override with POLICY_LLM_MODEL
    to the exact Hub-approved model id.
    """
    resolved_model = (
        model
        or os.environ.get("POLICY_LLM_MODEL")
        or os.environ.get("GUARDRAIL_MODEL")
        or "Llama-4-Scout"
    )
    resolved_narrative = (
        narrative_model
        or os.environ.get("POLICY_LLM_NARRATIVE_MODEL")
        or resolved_model
    )
    resolved_soeid = soeid or os.environ.get("SOEID") or os.environ.get("POLICY_SOEID")

    mod = backend if backend is not None else discover_guardrail_module()
    if mod is None:
        if require_live:
            raise GuardRailUnavailable(
                "GUARDRAIL_NOT_CONNECTED: GuardRail module not found. "
                "On CITI Hub, ensure GuardRail is importable; for offline tests use mock."
            )
        return MockLLMAdapter()

    create = getattr(mod, "CHAT_COMPLETIONS_CREATE", None)
    if not callable(create):
        if require_live:
            raise GuardRailUnavailable(
                "GUARDRAIL_NOT_CONNECTED: GuardRail module imported but "
                "CHAT_COMPLETIONS_CREATE is missing. See docs/guardrail_integration.md."
            )
        return MockLLMAdapter()

    try:
        return GuardRailClient(
            mod,
            model=str(resolved_model),
            narrative_model=str(resolved_narrative),
            soeid=resolved_soeid,
            temperature=temperature,
            max_retries=max_retries,
            extra_body=extra_body,
            parse_extra_body=parse_extra_body,
            n=n,
        )
    except GuardRailUnavailable:
        if require_live:
            raise
        return MockLLMAdapter()
