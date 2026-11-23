"""Pass F role relevance — schema, mock, no-invent validation."""

from __future__ import annotations

from pathlib import Path

from policy_knowledge.ingestion import read_policy
from policy_knowledge.intelligence.extraction_pipeline import extract_policy
from policy_knowledge.intelligence.role_relevance import (
    analyze_role_relevance,
    build_canonical_payload,
    export_role_relevance,
)
from policy_knowledge.intelligence.role_relevance_schemas import RoleRelevanceResult
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM
from policy_knowledge.validation.role_relevance_validator import (
    filter_role_relevance_result,
    validate_role_relevance,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _knowledge():
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    return extract_policy(
        blocks,
        SyntheticMockLLM(),
        policy_id="POLICY_001",
        title="Synthetic Escalation Policy",
    )


def test_analyze_role_relevance_mock_uses_only_real_ids(tmp_path: Path):
    knowledge = _knowledge()
    known = {
        *(r.id for r in knowledge.requirements),
        *(r.id for r in knowledge.roles),
        *(a.id for a in knowledge.actions),
        *(r.id for r in knowledge.risks),
        *(c.id for c in knowledge.controls),
        *(e.id for e in knowledge.evidence),
        *(f.id for f in knowledge.findings),
        *(d.id for d in knowledge.decisions),
    }
    source_ids = {b.id for b in knowledge.source_blocks}

    doc = analyze_role_relevance(
        knowledge,
        SyntheticMockLLM(),
        provider="mock",
        model="synthetic",
        temperature=0.0,
    )
    assert doc.policy_id == knowledge.policy.id
    assert doc.schema_version == "role_relevance-1.0"
    assert set(doc.perspectives.keys()) == {
        "business_owner",
        "compliance_officer",
        "policy_owner",
    }

    for name, perspective in doc.perspectives.items():
        assert perspective.assessments, f"{name} should have assessments"
        for item in perspective.assessments:
            assert item.artifact_id in known
            assert item.relevance in {
                "PRIMARY",
                "SECONDARY",
                "NOT_RELEVANT",
                "UNCERTAIN",
            }
            assert item.interpretation_basis in {"explicit", "inferred"}
            for ref in item.source_refs:
                assert ref in source_ids
            for aid in item.associated_action_ids:
                assert aid in known
            for rid in item.associated_risk_ids:
                assert rid in known
            for cid in item.associated_control_ids:
                assert cid in known
            for eid in item.associated_evidence_ids:
                assert eid in known

    report = validate_role_relevance(doc, knowledge)
    assert report.ok, report.errors

    out = export_role_relevance(doc, tmp_path / "role_relevance.json")
    assert out.exists()
    assert "business_owner" in out.read_text(encoding="utf-8")


def test_filter_drops_invented_artifact_ids():
    knowledge = _knowledge()
    fake = RoleRelevanceResult.model_validate(
        {
            "business_owner": {
                "assessments": [
                    {
                        "artifact_id": "REQ-FAKE",
                        "artifact_type": "requirement",
                        "relevance": "PRIMARY",
                        "why_relevant": "invented",
                        "interpretation_basis": "inferred",
                        "associated_control_ids": ["CTL-FAKE"],
                        "source_refs": ["SRC-FAKE"],
                    }
                ]
            }
        }
    )
    cleaned, notes = filter_role_relevance_result(fake, knowledge)
    assert cleaned.business_owner.assessments == []
    assert any("REQ-FAKE" in n for n in notes)


def test_canonical_payload_truncates_long_text():
    knowledge = _knowledge()
    if knowledge.requirements:
        knowledge.requirements[0].text = "x" * 600
    payload = build_canonical_payload(knowledge)
    assert len(payload["requirements"][0]["text"]) <= 501
