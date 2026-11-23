"""Assemble a simple QA quality report dict."""

from __future__ import annotations

from policy_knowledge.model.schemas import PolicyKnowledge
from policy_knowledge.validation.graph_validator import validate_graph_integrity
from policy_knowledge.validation.schema_validator import validate_knowledge


def build_quality_report(knowledge: PolicyKnowledge) -> dict:
    schema = validate_knowledge(knowledge)
    graph = validate_graph_integrity(knowledge)
    return {
        "schema": schema.to_dict(),
        "graph": graph.to_dict(),
        "finding_count": len(knowledge.findings),
        "requirement_count": len(knowledge.requirements),
        "edge_count": len(knowledge.edges),
        "inferred_edge_count": sum(
            1 for e in knowledge.edges if e.derivation == "inferred_for_review"
        ),
    }
