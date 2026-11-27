"""Risk taxonomy wiring: exact/alias deterministic, LLM candidate gated by the taxonomy list."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from policy_knowledge.governance.taxonomy_mapper import resolve_match
from policy_knowledge.ingestion import read_policy
from policy_knowledge.intelligence.extraction_pipeline import extract_policy
from policy_knowledge.intelligence.pass_schemas import PassCResult, PassCRisk
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def taxonomy_file(tmp_path: Path) -> Path:
    path = tmp_path / "risk_taxonomy.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "test",
                "risks": [
                    {"id": "RISK_OPS", "label": "Operational Risk", "aliases": ["ops risk"]},
                    {"id": "RISK_CONDUCT", "label": "Conduct Risk", "aliases": ["conduct"]},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_resolve_exact_alias_llm_and_unmapped(taxonomy_file: Path):
    assert resolve_match("Operational Risk", None, taxonomy_file, "risks").status == "exact"
    assert resolve_match("ops risk", None, taxonomy_file, "risks").status == "alias"

    suggested = resolve_match("Delayed escalation", "RISK_CONDUCT", taxonomy_file, "risks")
    assert suggested.status == "llm_suggested"
    assert suggested.code == "RISK_CONDUCT"

    invented = resolve_match("Delayed escalation", "RISK_MADE_UP", taxonomy_file, "risks")
    assert invented.status == "unmapped"
    assert invented.code is None

    assert resolve_match("Delayed escalation", None, taxonomy_file, "risks").status == "unmapped"
    assert resolve_match("", None, taxonomy_file, "risks").status == "not_specified"


class _TaxonomyRiskLLM(SyntheticMockLLM):
    def __init__(self, risks: list[PassCRisk]):
        super().__init__()
        self._risks = risks

    def parse_structured(self, messages, schema, **kwargs):
        if schema is PassCResult:
            return PassCResult(risks=self._risks)
        return super().parse_structured(messages, schema, **kwargs)


def test_pipeline_sets_risk_code_and_rejects_invented_ids(taxonomy_file: Path):
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    ref = blocks[0].id
    llm = _TaxonomyRiskLLM(
        [
            PassCRisk(name="Operational Risk", source_refs=[ref]),
            PassCRisk(name="Delayed escalation", source_refs=[ref], taxonomy_candidate_id="RISK_CONDUCT"),
            PassCRisk(name="Unclear exposure", source_refs=[ref], taxonomy_candidate_id="RISK_MADE_UP"),
        ]
    )
    knowledge = extract_policy(
        blocks,
        llm,
        policy_id="POLICY_TAX",
        title="Taxonomy test",
        risk_taxonomy_path=taxonomy_file,
    )
    by_name = {r.name: r for r in knowledge.risks}

    assert by_name["Operational Risk"].risk_code == "RISK_OPS"
    assert by_name["Operational Risk"].classification_origin == "normalized"
    assert by_name["Delayed escalation"].risk_code == "RISK_CONDUCT"
    assert by_name["Delayed escalation"].classification_origin == "suggested"
    assert by_name["Unclear exposure"].risk_code is None
    assert "RISK_MADE_UP" not in {r.risk_code for r in knowledge.risks}

    unmapped = [f for f in knowledge.findings if f.category == "unmapped_risk"]
    assert len(unmapped) == 1
    assert unmapped[0].entity_ids == [by_name["Unclear exposure"].id]

    assert by_name["Operational Risk"].risk_label == "Operational Risk"
    assert by_name["Delayed escalation"].risk_label == "Conduct Risk"
