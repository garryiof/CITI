"""Source traceability checks."""

from __future__ import annotations

from pathlib import Path

from policy_knowledge.ingestion import read_policy
from policy_knowledge.intelligence.extraction_pipeline import extract_policy
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM
from policy_knowledge.validation.graph_validator import validate_graph_integrity

FIXTURES = Path(__file__).parent / "fixtures"


def test_every_entity_grounded_in_known_source():
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    knowledge = extract_policy(
        blocks,
        SyntheticMockLLM(),
        policy_id="POLICY_001",
        title="Synthetic Escalation Policy",
    )
    available = {b.id for b in knowledge.source_blocks}
    for collection in (
        knowledge.requirements,
        knowledge.roles,
        knowledge.actions,
        knowledge.risks,
        knowledge.controls,
        knowledge.evidence,
    ):
        for ent in collection:
            assert ent.source_refs
            assert all(ref in available for ref in ent.source_refs)

    report = validate_graph_integrity(knowledge)
    assert report.ok
