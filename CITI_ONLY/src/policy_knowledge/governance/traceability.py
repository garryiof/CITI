"""Entity → source_ref traceability rows."""

from __future__ import annotations

from policy_knowledge.model.schemas import PolicyKnowledge


def build_traceability_rows(knowledge: PolicyKnowledge) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    collections = [
        ("requirement", knowledge.requirements),
        ("role", knowledge.roles),
        ("action", knowledge.actions),
        ("risk", knowledge.risks),
        ("control", knowledge.controls),
        ("evidence", knowledge.evidence),
    ]
    source_text = {b.id: b.text for b in knowledge.source_blocks}
    for kind, items in collections:
        for item in items:
            label = getattr(item, "text", None) or getattr(item, "name", None) or getattr(item, "label", "")
            for ref in item.source_refs:
                rows.append(
                    {
                        "entity_type": kind,
                        "entity_id": item.id,
                        "entity_label": str(label)[:200],
                        "source_ref": ref,
                        "source_excerpt": source_text.get(ref, "")[:300],
                    }
                )
    return rows
