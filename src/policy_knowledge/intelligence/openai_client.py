"""Optional OpenAI adapter for home / local full-pipeline runs.

Requires the `openai` package and OPENAI_API_KEY. Not used on Hub GuardRail path.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from pydantic import BaseModel


class OpenAIUnavailable(RuntimeError):
    """Raised when OpenAI provider is selected but cannot be used."""


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


class OpenAIAdapter:
    """Live OpenAI Chat Completions adapter implementing LLMAdapter."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        narrative_model: str | None = None,
        temperature: float = 0.0,
        max_retries: int = 3,
        extra_body: dict[str, Any] | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.narrative_model = narrative_model or model
        self.temperature = temperature
        self.max_retries = max_retries
        self.extra_body = dict(extra_body or {})
        self._client = client
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if self._client is None and not self._api_key:
            raise OpenAIUnavailable(
                "OPENAI_NOT_CONNECTED: OPENAI_API_KEY is not set. "
                "Export the key locally or switch llm.provider to mock/guardrail."
            )

    @classmethod
    def from_config(cls, llm_config: Any, *, client: Any | None = None) -> OpenAIAdapter:
        model = (
            getattr(llm_config, "model", None)
            or os.environ.get("OPENAI_MODEL")
            or os.environ.get("POLICY_LLM_MODEL")
            or "gpt-4o-mini"
        )
        narrative = getattr(llm_config, "narrative_model", None) or model
        return cls(
            model=str(model),
            narrative_model=str(narrative) if narrative else str(model),
            temperature=float(getattr(llm_config, "temperature", 0.0) or 0.0),
            max_retries=int(getattr(llm_config, "max_retries", 3) or 3),
            extra_body=dict(getattr(llm_config, "extra_body", None) or {}),
            client=client,
        )

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as exc:
            raise OpenAIUnavailable(
                "OPENAI_NOT_CONNECTED: `openai` package is not installed. "
                "Install locally for home runs (`pip install openai`); "
                "Hub path should use llm.provider=guardrail or mock."
            ) from exc
        self._client = OpenAI(api_key=self._api_key)
        return self._client

    def _create(self, messages: list[dict], *, model: str, response_format: dict | None = None) -> str:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        kwargs.update(self.extra_body)
        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        content = getattr(choice.message, "content", None)
        if not content:
            raise RuntimeError("OpenAI returned empty content")
        return str(content)

    def generate_text(self, messages: list[dict], **kwargs: Any) -> str:
        model = str(kwargs.get("model") or self.model)
        return self._create(messages, model=model)

    def generate_narrative(self, messages: list[dict], **kwargs: Any) -> str:
        model = str(kwargs.get("model") or self.narrative_model)
        return self._create(messages, model=model)

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

        last_error: Exception | None = None
        attempts = 0
        while attempts <= max_retries:
            attempts += 1
            try:
                raw = self._create(
                    enriched,
                    model=model,
                    response_format={"type": "json_object"},
                )
                data = json.loads(raw)
                return schema.model_validate(data)
            except Exception as exc:  # noqa: BLE001 — retry then surface
                last_error = exc
                if attempts <= max_retries:
                    time.sleep(min(0.5 * attempts, 2.0))
                    continue
                raise
        assert last_error is not None
        raise last_error
