"""Schema-level validation of PolicyKnowledge."""

from __future__ import annotations

from dataclasses import dataclass, field

from policy_knowledge.model.schemas import PolicyKnowledge

APPROVED_RELATIONS = {
    "POLICY_CONTAINS_SECTION",
    "SECTION_STATES_REQUIREMENT",
    "REQUIREMENT_REQUIRES_ACTION",
    "ROLE_PERFORMS_ACTION",
    "ROLE_OWNS_CONTROL",
    "ACTION_PART_OF_PROCESS",
    "ACTION_PRECEDES_ACTION",
    "DECISION_BRANCHES_TO_ACTION",
    "REQUIREMENT_ADDRESSES_RISK",
    "CONTROL_MITIGATES_RISK",
    "ACTION_EXECUTES_CONTROL",
    "CONTROL_PRODUCES_EVIDENCE",
    "EVIDENCE_SUPPORTS_CONTROL",
    "ENTITY_GROUNDED_IN_SOURCE",
}


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def validate_knowledge(knowledge: PolicyKnowledge) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    if not knowledge.policy.id:
        errors.append("policy.id required")
    if not knowledge.source_blocks:
        warnings.append("no source_blocks")
    source_ids = {b.id for b in knowledge.source_blocks}
    for req in knowledge.requirements:
        if not req.source_refs:
            errors.append(f"requirement {req.id} missing source_refs")
        elif any(r not in source_ids for r in req.source_refs):
            errors.append(f"requirement {req.id} has unknown source_refs")
    for edge in knowledge.edges:
        if edge.relation_type not in APPROVED_RELATIONS:
            errors.append(f"unknown relation_type {edge.relation_type}")
    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)
