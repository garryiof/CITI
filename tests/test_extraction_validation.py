"""Extraction pipeline + response validation."""

from __future__ import annotations

from pathlib import Path

from policy_knowledge.ingestion import read_policy
from policy_knowledge.intelligence.extraction_pipeline import extract_policy
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM
from policy_knowledge.validation.schema_validator import validate_knowledge

FIXTURES = Path(__file__).parent / "fixtures"


def test_synthetic_extraction_has_citations_and_stable_ids():
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    llm = SyntheticMockLLM()
    k1 = extract_policy(blocks, llm, policy_id="POLICY_001", title="Synthetic Escalation Policy")
    k2 = extract_policy(blocks, llm, policy_id="POLICY_001", title="Synthetic Escalation Policy")

    assert k1.requirements
    assert k1.roles
    assert k1.actions
    assert all(r.source_refs for r in k1.requirements)
    assert all(a.source_refs for a in k1.actions)
    assert [r.id for r in k1.requirements] == [r.id for r in k2.requirements]
    assert [e.id for e in k1.edges] == [e.id for e in k2.edges]

    report = validate_knowledge(k1)
    assert report.ok


def test_uncited_entities_rejected_when_required():
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    llm = SyntheticMockLLM(inject_uncited=True)
    knowledge = extract_policy(
        blocks,
        llm,
        policy_id="POLICY_001",
        title="Synthetic Escalation Policy",
        require_source_refs=True,
    )
    assert any(f.category == "missing_source_ref" for f in knowledge.findings)
    assert all(r.source_refs for r in knowledge.requirements)


def test_inferred_edges_flagged_and_no_invented_frequency():
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    knowledge = extract_policy(
        blocks,
        SyntheticMockLLM(),
        policy_id="POLICY_001",
        title="Synthetic Escalation Policy",
    )
    inferred = [e for e in knowledge.edges if e.derivation == "inferred_for_review"]
    assert inferred
    for ctl in knowledge.controls:
        # Frequency only when source states it (synthetic says "each occurrence")
        if ctl.frequency is not None:
            assert "occurrence" in ctl.frequency.lower() or ctl.frequency == "not_specified"


def test_nonprocedural_modeling_status():
    blocks = read_policy(FIXTURES / "synthetic_policy_nonprocedural.html")
    knowledge = extract_policy(
        blocks,
        SyntheticMockLLM(mode="nonprocedural"),
        policy_id="POLICY_NP",
        title="Synthetic Principles Policy",
    )
    assert knowledge.processes
    assert knowledge.processes[0].modeling_status == "unsupported"
    assert not knowledge.actions or all(
        "procedure" not in (a.label or "").lower() for a in knowledge.actions
    )
