"""Regression: Pass B returning an empty action list for a supported procedure."""

from __future__ import annotations

from pathlib import Path

from policy_knowledge.ingestion import read_policy
from policy_knowledge.intelligence.extraction_pipeline import extract_policy
from policy_knowledge.intelligence.pass_schemas import PassBResult
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM

FIXTURES = Path(__file__).parent / "fixtures"


class _EmptyPassBLLM(SyntheticMockLLM):
    """Reproduces the Hub reply: supported, no actions, one empty flow object."""

    def parse_structured(self, messages, schema, **kwargs):
        if schema is PassBResult:
            return PassBResult(
                process_name="Personal Trading and Investment Policy",
                modeling_status="supported",
                actions=[],
                decisions=[],
                flow=[{}],
            )
        return super().parse_structured(messages, schema, **kwargs)


def _extract(llm):
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    return extract_policy(
        blocks,
        llm,
        policy_id="POLICY_001",
        title="Synthetic Escalation Policy",
    )


def test_empty_pass_b_actions_is_reported():
    knowledge = _extract(_EmptyPassBLLM())
    categories = [f.category for f in knowledge.findings]
    assert "empty_pass_b_actions" in categories


def test_empty_flow_objects_are_dropped():
    knowledge = _extract(_EmptyPassBLLM())
    assert knowledge.processes[0].flow_relations == []
