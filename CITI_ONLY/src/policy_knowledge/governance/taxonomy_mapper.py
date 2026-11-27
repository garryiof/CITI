"""Exact / alias / unmapped taxonomy mapping — never silent invent.

Taxonomy files are loaded from ``CITI_TAXONOMY_DIR`` when set (keep the real CITI
taxonomy outside the public repo), otherwise from the repo ``config/`` folder.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

TAXONOMY_DIR_ENV = "CITI_TAXONOMY_DIR"


@dataclass
class TaxonomyMatch:
    status: str  # exact | alias | llm_suggested | unmapped | not_specified
    code: Optional[str] = None
    label: Optional[str] = None
    input_label: str = ""


def default_taxonomy_dir() -> Path:
    env = os.environ.get(TAXONOMY_DIR_ENV)
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "config"


def load_entries(path: Path, key: str) -> list[dict[str, Any]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return list(data.get(key) or [])


def _load_entries(path: Path, key: str) -> list[dict[str, Any]]:
    return load_entries(path, key)


def map_label(label: Optional[str], path: Path, key: str) -> TaxonomyMatch:
    if label is None or not str(label).strip():
        return TaxonomyMatch(status="not_specified", input_label=label or "")
    needle = label.strip().lower()
    for entry in _load_entries(path, key):
        code = entry.get("id")
        entry_label = str(entry.get("label", ""))
        aliases = [a.lower() for a in entry.get("aliases") or []]
        if entry_label.lower() == needle:
            return TaxonomyMatch(status="exact", code=code, label=entry_label, input_label=label)
        if needle == str(code).lower():
            return TaxonomyMatch(status="exact", code=code, label=entry_label, input_label=label)
        if needle in aliases:
            return TaxonomyMatch(status="alias", code=code, label=entry_label, input_label=label)
    return TaxonomyMatch(status="unmapped", input_label=label)


def resolve_match(
    label: Optional[str],
    candidate_id: Optional[str],
    path: Path,
    key: str,
) -> TaxonomyMatch:
    """Deterministic exact/alias first; an LLM candidate is accepted only if it is a real taxonomy id."""
    matched = map_label(label, path, key)
    if matched.status in ("exact", "alias", "not_specified"):
        return matched
    if candidate_id:
        wanted = str(candidate_id).strip()
        for entry in _load_entries(path, key):
            if str(entry.get("id")) == wanted:
                return TaxonomyMatch(
                    status="llm_suggested",
                    code=wanted,
                    label=str(entry.get("label", "")),
                    input_label=label or "",
                )
    return matched


def map_role_label(label: Optional[str], taxonomy_path: Path) -> TaxonomyMatch:
    return map_label(label, taxonomy_path, "roles")


def map_risk_label(label: Optional[str], taxonomy_path: Path) -> TaxonomyMatch:
    return map_label(label, taxonomy_path, "risks")


def map_control_label(label: Optional[str], taxonomy_path: Path) -> TaxonomyMatch:
    return map_label(label, taxonomy_path, "controls")
