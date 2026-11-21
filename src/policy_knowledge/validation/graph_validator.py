"""Graph integrity validation."""

from __future__ import annotations

from policy_knowledge.model.graph import build_knowledge_graph
from policy_knowledge.model.schemas import PolicyKnowledge
from policy_knowledge.validation.schema_validator import ValidationReport


def validate_graph_integrity(knowledge: PolicyKnowledge) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    node_ids = set()
    for collection in (
        [knowledge.policy],
        knowledge.source_blocks,
        knowledge.requirements,
        knowledge.roles,
        knowledge.actions,
        knowledge.processes,
        knowledge.decisions,
        knowledge.risks,
        knowledge.controls,
        knowledge.evidence,
    ):
        for item in collection:
            node_ids.add(item.id)

    for edge in knowledge.edges:
        if edge.source_id not in node_ids and not edge.source_id.startswith("SRC-"):
            # Edges may reference names resolved earlier; warn if dangling.
            if edge.source_id not in node_ids:
                warnings.append(f"edge {edge.id} source not in node set: {edge.source_id}")
        if edge.target_id not in node_ids and not edge.target_id.startswith("SRC-"):
            if edge.target_id not in node_ids:
                warnings.append(f"edge {edge.id} target not in node set: {edge.target_id}")

    # Ensure graph builds
    g = build_knowledge_graph(knowledge)
    if not g.has_node(knowledge.policy.id):
        errors.append("policy node missing from graph")
    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)
