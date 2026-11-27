"""Pass F — role-based policy intelligence over canonical artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from policy_knowledge.intelligence.guardrail_client import LLMAdapter, build_messages
from policy_knowledge.intelligence.prompt_loader import load_prompt, prompt_execution_metadata
from policy_knowledge.intelligence.role_relevance_schemas import (
    RoleAssessment,
    RoleRelevanceDocument,
    RoleRelevanceResult,
)
from policy_knowledge.model.schemas import PolicyKnowledge
from policy_knowledge.validation.role_relevance_validator import (
    filter_role_relevance_result,
    validate_role_relevance,
)

_TEXT_LIMIT = 500


def _truncate(text: Optional[str], limit: int = _TEXT_LIMIT) -> str:
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "…"


def build_canonical_payload(knowledge: PolicyKnowledge) -> dict[str, Any]:
    """Compact canonical dump for the Pass F user prompt."""
    return {
        "policy": {
            "id": knowledge.policy.id,
            "title": knowledge.policy.title,
        },
        "requirements": [
            {
                "id": r.id,
                "text": _truncate(r.text),
                "modality": r.modality,
                "source_refs": list(r.source_refs),
            }
            for r in knowledge.requirements
        ],
        "roles": [
            {
                "id": r.id,
                "name": r.name,
                "description": _truncate(r.description),
                "source_refs": list(r.source_refs),
            }
            for r in knowledge.roles
        ],
        "actions": [
            {
                "id": a.id,
                "label": a.label,
                "description": _truncate(a.description),
                "actor_role_ids": list(a.actor_role_ids),
                "source_refs": list(a.source_refs),
            }
            for a in knowledge.actions
        ],
        "decisions": [
            {
                "id": d.id,
                "question": _truncate(d.question),
                "source_refs": list(d.source_refs),
            }
            for d in knowledge.decisions
        ],
        "risks": [
            {
                "id": r.id,
                "name": r.name,
                "risk_code": r.risk_code,
                "description": _truncate(r.description),
                "source_refs": list(r.source_refs),
            }
            for r in knowledge.risks
        ],
        "controls": [
            {
                "id": c.id,
                "name": c.name,
                "description": _truncate(c.description),
                "owner_role_ids": list(c.owner_role_ids),
                "frequency": c.frequency,
                "source_refs": list(c.source_refs),
            }
            for c in knowledge.controls
        ],
        "evidence": [
            {
                "id": e.id,
                "name": e.name,
                "description": _truncate(e.description),
                "related_control_ids": list(e.related_control_ids),
                "source_refs": list(e.source_refs),
            }
            for e in knowledge.evidence
        ],
        "edges": [
            {
                "id": e.id,
                "source_id": e.source_id,
                "target_id": e.target_id,
                "relation_type": e.relation_type,
                "derivation": e.derivation,
            }
            for e in knowledge.edges
        ],
        "findings": [
            {
                "id": f.id,
                "severity": f.severity,
                "category": f.category,
                "description": _truncate(f.description),
                "entity_ids": list(f.entity_ids),
                "source_refs": list(f.source_refs),
            }
            for f in knowledge.findings
        ],
    }


def _synthetic_role_relevance(knowledge: PolicyKnowledge) -> RoleRelevanceResult:
    """Deterministic Pass F when the adapter is SyntheticMockLLM-compatible."""
    from policy_knowledge.intelligence.synthetic_mock import build_synthetic_role_relevance

    return build_synthetic_role_relevance(knowledge)


def analyze_role_relevance(
    knowledge: PolicyKnowledge,
    llm: LLMAdapter,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> RoleRelevanceDocument:
    """Run Pass F and return a validated RoleRelevanceDocument."""
    system = load_prompt("role_relevance.system")
    user = load_prompt(
        "role_relevance.user",
        variables={
            "policy_id": knowledge.policy.id,
            "policy_title": knowledge.policy.title,
            "canonical_json": json.dumps(
                build_canonical_payload(knowledge),
                ensure_ascii=False,
            ),
        },
    )
    messages = build_messages(system.text, user.text.rstrip("\n"))

    # Prefer structured parse; SyntheticMockLLM handles RoleRelevanceResult.
    try:
        raw = llm.parse_structured(messages, RoleRelevanceResult)
    except TypeError:
        # Adapters that only know Passes A–E fall back to deterministic mapping.
        raw = _synthetic_role_relevance(knowledge)

    if not isinstance(raw, RoleRelevanceResult):
        raw = RoleRelevanceResult.model_validate(raw)

    filtered, drop_notes = filter_role_relevance_result(raw, knowledge)
    generated_at = datetime.now(timezone.utc).isoformat()
    doc = RoleRelevanceDocument(
        policy_id=knowledge.policy.id,
        generated_at=generated_at,
        prompt={"id": system.id, "version": system.version, "user_version": user.version},
        llm={
            **prompt_execution_metadata(
                system,
                user,
                provider=provider,
                model=model,
                temperature=temperature,
            ),
            "filter_notes": drop_notes,
        },
        perspectives={
            "business_owner": filtered.business_owner,
            "compliance_officer": filtered.compliance_officer,
            "policy_owner": filtered.policy_owner,
        },
    )
    report = validate_role_relevance(doc, knowledge)
    if not report.ok:
        # Soft-fail: strip invalid assessments already filtered; surface as llm notes.
        doc.llm = {**dict(doc.llm), "validation_errors": report.errors}
    return doc


def export_role_relevance(doc: RoleRelevanceDocument, path: Any) -> Any:
    from pathlib import Path

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    return out
