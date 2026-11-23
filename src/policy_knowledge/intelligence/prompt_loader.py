"""External prompt loader with variable substitution and version metadata."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Union

PROMPTS_DIR = Path(__file__).parent / "prompts"
_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class PromptError(ValueError):
    """Raised when a prompt cannot be loaded, validated, or rendered."""


@dataclass(frozen=True)
class PromptTemplate:
    id: str
    version: str
    text: str
    required_vars: tuple[str, ...]
    path: Path
    description: str = ""

    def render(self, variables: Optional[dict[str, Any]] = None) -> str:
        return render_template(self.text, variables or {}, required_vars=self.required_vars)


@lru_cache(maxsize=1)
def _load_manifest(prompts_dir: str) -> dict[str, Any]:
    path = Path(prompts_dir) / "manifest.json"
    if not path.exists():
        raise PromptError(f"Prompt manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if "prompts" not in data or not isinstance(data["prompts"], dict):
        raise PromptError("Prompt manifest must contain a 'prompts' object")
    return data


def clear_prompt_cache() -> None:
    """Test helper — reset cached manifest."""
    _load_manifest.cache_clear()


def list_prompt_ids(*, prompts_dir: Optional[Path] = None) -> list[str]:
    root = Path(prompts_dir or PROMPTS_DIR)
    manifest = _load_manifest(str(root.resolve()))
    return sorted(manifest["prompts"].keys())


def load_prompt(
    prompt_id: str,
    *,
    variables: Optional[dict[str, Any]] = None,
    prompts_dir: Optional[Path] = None,
) -> PromptTemplate:
    """Load a prompt by id from manifest.json and optionally render variables."""
    root = Path(prompts_dir or PROMPTS_DIR)
    manifest = _load_manifest(str(root.resolve()))
    entry = manifest["prompts"].get(prompt_id)
    if entry is None:
        # Legacy alias: pass_a.md → pass_a.system
        alias = manifest.get("aliases", {}).get(prompt_id)
        if alias:
            return load_prompt(alias, variables=variables, prompts_dir=root)
        raise PromptError(f"Unknown prompt id: {prompt_id}")

    rel = entry.get("file")
    if not rel:
        raise PromptError(f"Prompt {prompt_id} missing 'file' in manifest")
    path = root / rel
    if not path.exists():
        raise PromptError(f"Prompt file not found for {prompt_id}: {path}")

    text = path.read_text(encoding="utf-8")
    required = tuple(entry.get("required_vars") or [])
    template = PromptTemplate(
        id=prompt_id,
        version=str(entry.get("version") or "0.0.0"),
        text=text,
        required_vars=required,
        path=path,
        description=str(entry.get("description") or ""),
    )
    if variables is not None:
        rendered = template.render(variables)
        return PromptTemplate(
            id=template.id,
            version=template.version,
            text=rendered,
            required_vars=template.required_vars,
            path=template.path,
            description=template.description,
        )
    return template


def render_template(
    text: str,
    variables: dict[str, Any],
    *,
    required_vars: Union[tuple[str, ...], list[str]] = (),
) -> str:
    """Substitute {{var}} placeholders; fail on missing required or unknown vars."""
    found = set(_VAR_PATTERN.findall(text))
    required = set(required_vars)
    missing_required = required - set(variables.keys())
    if missing_required:
        raise PromptError(f"Missing required prompt variables: {sorted(missing_required)}")
    unknown = found - set(variables.keys())
    if unknown:
        raise PromptError(f"Unknown prompt variables in template: {sorted(unknown)}")

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = variables[key]
        return "" if value is None else str(value)

    return _VAR_PATTERN.sub(_replace, text)


def prompt_execution_metadata(
    *templates: PromptTemplate,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> dict[str, Any]:
    """Compact execution metadata for run artifacts (no full prompt bodies)."""
    return {
        "prompts": [
            {"id": t.id, "version": t.version, "file": str(t.path.name)} for t in templates
        ],
        "provider": provider,
        "model": model,
        "temperature": temperature,
    }
