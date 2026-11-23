"""Risk / control / requirement / process link rows."""

from __future__ import annotations

from policy_knowledge.model.schemas import PolicyKnowledge


def build_risk_control_rows(knowledge: PolicyKnowledge) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for risk in knowledge.risks:
        mitigations = [
            e.source_id
            for e in knowledge.edges
            if e.relation_type == "CONTROL_MITIGATES_RISK" and e.target_id == risk.id
        ]
        reqs = [
            e.source_id
            for e in knowledge.edges
            if e.relation_type == "REQUIREMENT_ADDRESSES_RISK" and e.target_id == risk.id
        ]
        rows.append(
            {
                "risk_id": risk.id,
                "risk_name": risk.name,
                "controls": ";".join(mitigations) or "not_specified",
                "requirements": ";".join(reqs) or "not_specified",
                "origin": risk.classification_origin,
            }
        )
    return rows
