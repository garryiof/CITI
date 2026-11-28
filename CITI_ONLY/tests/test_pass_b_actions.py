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


def test_chunked_pass_b_extracts_and_merges_across_chunks():
    from policy_knowledge.intelligence.extraction_pipeline import _blocks_payload
    from policy_knowledge.intelligence.pass_schemas import PassWResult
    from policy_knowledge.intelligence.synthetic_mock import _blocks_from_messages
    from policy_knowledge.model.schemas import SourceBlock

    class _ChunkAwareLLM(SyntheticMockLLM):
        def __init__(self) -> None:
            super().__init__()
            self.pass_b_calls = 0

        def parse_structured(self, messages, schema, **kwargs):
            if schema is PassBResult:
                self.pass_b_calls += 1
                blocks = _blocks_from_messages(messages)
                joined = " ".join(b.get("text", "") for b in blocks).lower()
                actions = []
                decisions = []
                flow = []
                if "reportable accounts" in joined:
                    ref = next(b["id"] for b in blocks if "reportable accounts" in b["text"].lower())
                    actions.extend([
                        {
                            "label": "Obtain ICRM approval for new Reportable Accounts",
                            "description": "Obtain ICRM approval prior to opening a new Reportable Account.",
                            "actor_role_names": ["Process Performer"],
                            "source_refs": [ref],
                        },
                        {
                            "label": "Disclose Reportable Accounts",
                            "description": "Disclose all Reportable Accounts within 10 business days.",
                            "actor_role_names": ["Process Performer"],
                            "source_refs": [ref],
                        },
                    ])
                    flow.append({
                        "from": "Obtain ICRM approval for new Reportable Accounts",
                        "to": "Disclose Reportable Accounts",
                    })
                if "pre-clearance" in joined:
                    ref = next(b["id"] for b in blocks if "pre-clearance" in b["text"].lower())
                    actions.extend([
                        {
                            "label": "Submit pre-clearance request",
                            "description": "Submit a pre-clearance request before placing any trade.",
                            "actor_role_names": ["Process Performer"],
                            "source_refs": [ref],
                        },
                        {
                            "label": "Execute approved trade",
                            "description": "Execute the security trade within the approval window.",
                            "actor_role_names": ["Process Performer"],
                            "source_refs": [ref],
                        },
                    ])
                    decisions.append({
                        "question": "Is the Covered Person eligible to trade in a particular security?",
                        "after_action_label": "Submit pre-clearance request",
                        "branches": [
                            {"condition": "Approved", "outcome": "PROCEED", "next_action_label": "Execute approved trade"},
                            {"condition": "Rejected / Prohibited", "outcome": "PROHIBITED", "next_action_label": None},
                        ],
                        "source_refs": [ref],
                    })
                    flow.append({"from": "Submit pre-clearance request", "to": "Execute approved trade"})
                return PassBResult(
                    process_name="Personal Trading",
                    modeling_status="supported",
                    actions=actions,
                    decisions=decisions,
                    flow=flow,
                )
            if schema is PassWResult:
                # Omit one action deliberately to verify catch-all workflow keeps every action.
                return PassWResult.model_validate({
                    "workflows": [
                        {
                            "title": "Reportable account disclosure",
                            "summary": "Approve and disclose reportable accounts.",
                            "trigger": "Opening a reportable account.",
                            "action_labels": [
                                "Obtain ICRM approval for new Reportable Accounts",
                                "Disclose Reportable Accounts",
                            ],
                        },
                        {
                            "title": "Pre-clearance trading",
                            "summary": "Request pre-clearance before trading.",
                            "trigger": "Planning a trade.",
                            "action_labels": ["Submit pre-clearance request"],
                        },
                    ]
                })
            return super().parse_structured(messages, schema, **kwargs)

    blocks = [
        SourceBlock(
            id="SRC-0001",
            policy_id="PTIP",
            section_path="1. Accounts",
            text=("Covered Persons must obtain ICRM approval and disclose Reportable Accounts. " * 6).strip(),
            block_type="section",
            source_locator="pdf:page[1]#s1",
            sequence=1,
            document_hash="h1",
        ),
        SourceBlock(
            id="SRC-0002",
            policy_id="PTIP",
            section_path="2. Trading",
            text=("Covered Persons must submit pre-clearance before executing any security trade. " * 6).strip(),
            block_type="section",
            source_locator="pdf:page[2]#s1",
            sequence=2,
            document_hash="h1",
        ),
    ]
    llm = _ChunkAwareLLM()
    knowledge = extract_policy(
        blocks,
        llm,
        policy_id="PTIP",
        title="Personal Trading Policy",
        max_chunk_chars=300,
    )
    assert llm.pass_b_calls >= 2
    labels = [a.label for a in knowledge.actions]
    assert "Obtain ICRM approval for new Reportable Accounts" in labels
    assert "Disclose Reportable Accounts" in labels
    assert "Submit pre-clearance request" in labels
    assert "Execute approved trade" in labels
    assert any(d.after_action_label == "Submit pre-clearance request" for d in knowledge.decisions)
    # Catch-all workflow ensures uncovered action is not lost from WF-* views.
    wf_action_ids = {aid for p in knowledge.processes[1:] for aid in p.activities}
    assert set(knowledge.processes[0].activities) == wf_action_ids

