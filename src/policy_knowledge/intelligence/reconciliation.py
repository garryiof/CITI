"""Dedupe and contradiction findings after multi-pass extraction."""

from __future__ import annotations

from policy_knowledge.model.schemas import PolicyKnowledge, ReviewFinding


def reconcile_knowledge(knowledge: PolicyKnowledge) -> PolicyKnowledge:
    knowledge.requirements = _dedupe_by(knowledge.requirements, key=lambda r: r.text.strip().lower())
    knowledge.roles = _dedupe_by(knowledge.roles, key=lambda r: r.name.strip().lower())
    knowledge.actions = _dedupe_by(knowledge.actions, key=lambda a: a.label.strip().lower())
    knowledge.risks = _dedupe_by(knowledge.risks, key=lambda r: r.name.strip().lower())
    knowledge.controls = _dedupe_by(knowledge.controls, key=lambda c: c.name.strip().lower())
    knowledge.evidence = _dedupe_by(knowledge.evidence, key=lambda e: e.name.strip().lower())

    # Pronoun / vague actor heuristic
    for action in knowledge.actions:
        if not action.actor_role_ids:
            knowledge.findings.append(
                ReviewFinding(
                    id=f"FIND-ACTOR-{action.id}",
                    severity="low",
                    category="missing_actor",
                    description=f"Action '{action.label}' has no actor role ids.",
                    entity_ids=[action.id],
                    source_refs=action.source_refs,
                    disposition="open",
                )
            )
    return knowledge


def _dedupe_by(items: list, key) -> list:
    seen: set[str] = set()
    out = []
    for item in items:
        k = key(item)
        if k in seen:
            continue
        seen.add(k)
        out.append(item)
    return out
