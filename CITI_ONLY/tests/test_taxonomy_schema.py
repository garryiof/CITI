"""Taxonomy files must match config/risk_taxonomy.schema.json (skipped if jsonschema is absent)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

jsonschema = pytest.importorskip("jsonschema")

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config"
SCHEMA = json.loads((REPO_CONFIG / "risk_taxonomy.schema.json").read_text(encoding="utf-8"))


def _validate(doc):
    jsonschema.validate(instance=doc, schema=SCHEMA)


def test_placeholder_risk_taxonomy_matches_schema():
    doc = yaml.safe_load((REPO_CONFIG / "risk_taxonomy.yaml").read_text(encoding="utf-8"))
    _validate(doc)


def test_valid_sample_with_all_optional_fields():
    _validate(
        {
            "version": "2026.1",
            "risks": [
                {
                    "id": "RISK_OPS",
                    "label": "Operational Risk",
                    "definition": "Loss from failed processes.",
                    "aliases": ["ops risk", "operational"],
                },
                {"id": "RISK_CONDUCT", "label": "Conduct Risk"},
            ],
        }
    )


def test_missing_label_is_rejected():
    with pytest.raises(jsonschema.ValidationError):
        _validate({"risks": [{"id": "RISK_OPS"}]})


def test_unknown_field_is_rejected():
    with pytest.raises(jsonschema.ValidationError):
        _validate({"risks": [{"id": "RISK_OPS", "label": "Operational Risk", "owner": "x"}]})


def _duplicate_ids(doc):
    # JSON Schema cannot enforce id uniqueness across list items, so check it here.
    seen, dupes = set(), []
    for entry in doc.get("risks", []):
        if entry["id"] in seen:
            dupes.append(entry["id"])
        seen.add(entry["id"])
    return dupes


def test_duplicate_ids_are_detected():
    doc = {"risks": [{"id": "RISK_OPS", "label": "A"}, {"id": "RISK_OPS", "label": "B"}]}
    _validate(doc)  # schema-valid, so only the uniqueness check catches it
    assert _duplicate_ids(doc) == ["RISK_OPS"]


def test_placeholder_risk_ids_are_unique():
    doc = yaml.safe_load((REPO_CONFIG / "risk_taxonomy.yaml").read_text(encoding="utf-8"))
    assert _duplicate_ids(doc) == []
