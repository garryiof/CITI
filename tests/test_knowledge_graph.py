"""Canonical model + stable IDs + graph helpers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from policy_knowledge.model.entity_ids import (
    stable_edge_id,
    stable_entity_id,
    stable_source_id,
)
from policy_knowledge.model.graph import build_knowledge_graph, to_cytoscape_elements
from policy_knowledge.model.schemas import (
    KnowledgeEdge,
    Policy,
    PolicyKnowledge,
    Requirement,
    SourceBlock,
)


def test_policy_requires_core_fields():
    with pytest.raises(ValidationError):
        Policy(id="P1")  # type: ignore[call-arg]


def test_source_block_requires_locator_and_sequence():
    with pytest.raises(ValidationError):
        SourceBlock(
            id="SRC-0001",
            policy_id="POLICY_001",
            section_path="1",
            text="x",
            block_type="paragraph",
        )  # type: ignore[call-arg]


def test_requirement_modality_enum():
    req = Requirement(
        id="REQ-1",
        text="Must escalate exceptions.",
        modality="must",
        type="obligation",
        source_refs=["SRC-0001"],
        review_status="extracted",
    )
    assert req.modality == "must"
    with pytest.raises(ValidationError):
        Requirement(
            id="REQ-2",
            text="x",
            modality="sometimes",
            type="obligation",
            source_refs=["SRC-0001"],
            review_status="extracted",
        )


def test_stable_source_id_deterministic():
    a = stable_source_id(
        document_hash="abc",
        locator="html:body/section[1]",
        text="Hello world",
        sequence=1,
    )
    b = stable_source_id(
        document_hash="abc",
        locator="html:body/section[1]",
        text="Hello world",
        sequence=1,
    )
    assert a == b
    assert a.startswith("SRC-")
    c = stable_source_id(
        document_hash="abc",
        locator="html:body/section[2]",
        text="Hello world",
        sequence=2,
    )
    assert a != c


def test_stable_entity_and_edge_ids_deterministic():
    e1 = stable_entity_id("requirement", "must escalate", "SRC-0001")
    e2 = stable_entity_id("requirement", "must escalate", "SRC-0001")
    assert e1 == e2
    edge_a = stable_edge_id("REQ-1", "REQUIREMENT_REQUIRES_ACTION", "ACT-1", "SRC-0001")
    edge_b = stable_edge_id("REQ-1", "REQUIREMENT_REQUIRES_ACTION", "ACT-1", "SRC-0001")
    assert edge_a == edge_b


def test_policy_knowledge_aggregate_and_graph():
    policy = Policy(
        id="POLICY_001",
        title="Synthetic Escalation Policy",
        input_path="tests/fixtures/synthetic_policy.html",
        source_hash="deadbeef",
        review_status="extracted",
    )
    block = SourceBlock(
        id="SRC-0001",
        policy_id="POLICY_001",
        section_path="1. Purpose",
        text="Analysts must escalate exceptions within 1 business day.",
        block_type="paragraph",
        source_locator="html:#s1-p1",
        sequence=1,
        document_hash="deadbeef",
    )
    req = Requirement(
        id="REQ-1",
        text="Analysts must escalate exceptions within 1 business day.",
        modality="must",
        type="obligation",
        source_refs=["SRC-0001"],
        review_status="extracted",
    )
    edge = KnowledgeEdge(
        id="EDGE-1",
        source_id="REQ-1",
        target_id="SRC-0001",
        relation_type="ENTITY_GROUNDED_IN_SOURCE",
        source_refs=["SRC-0001"],
        derivation="explicit",
        review_status="extracted",
    )
    knowledge = PolicyKnowledge(
        policy=policy,
        source_blocks=[block],
        requirements=[req],
        edges=[edge],
    )
    g = build_knowledge_graph(knowledge)
    assert g.has_node("REQ-1")
    assert g.has_edge("REQ-1", "SRC-0001")
    elements = to_cytoscape_elements(knowledge)
    assert any(el.get("data", {}).get("id") == "REQ-1" for el in elements)
