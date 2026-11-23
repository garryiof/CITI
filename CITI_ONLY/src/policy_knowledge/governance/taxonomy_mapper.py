"""Exact / alias / unmapped taxonomy mapping — never silent invent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class TaxonomyMatch:
    status: str  # exact | alias | unmapped | not_specified
    code: Optional[str] = None
    label: Optional[str] = None
    input_label: str = ""


def _load_entries(path: Path, key: str) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get(key) or [])


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


def map_role_label(label: Optional[str], taxonomy_path: Path) -> TaxonomyMatch:
    return map_label(label, taxonomy_path, "roles")


def map_risk_label(label: Optional[str], taxonomy_path: Path) -> TaxonomyMatch:
    return map_label(label, taxonomy_path, "risks")


def map_control_label(label: Optional[str], taxonomy_path: Path) -> TaxonomyMatch:
    return map_label(label, taxonomy_path, "controls")
