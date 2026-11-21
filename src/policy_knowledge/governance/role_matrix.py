"""Role × requirement/action/control matrix rows."""

from __future__ import annotations

from policy_knowledge.model.schemas import PolicyKnowledge


def build_role_matrix_rows(knowledge: PolicyKnowledge) -> list[dict[str, str]]:
    role_names = {r.id: r.name for r in knowledge.roles}
    rows: list[dict[str, str]] = []
    for role in knowledge.roles:
        linked_reqs = [
            e.source_id
            for e in knowledge.edges
            if e.relation_type == "ROLE_PERFORMS_ACTION" and e.source_id == role.id
        ]
        owned = [
            e.target_id
            for e in knowledge.edges
            if e.relation_type == "ROLE_OWNS_CONTROL" and e.source_id == role.id
        ]
        rows.append(
            {
                "role_id": role.id,
                "role_name": role.name,
                "performs_actions": ";".join(linked_reqs) or "not_specified",
                "owns_controls": ";".join(owned) or "not_specified",
                "taxonomy": role.taxonomy_code or "unmapped",
            }
        )
    _ = role_names
    return rows
