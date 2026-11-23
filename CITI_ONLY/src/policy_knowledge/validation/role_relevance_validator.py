"""Validate role_relevance artifacts against PolicyKnowledge IDs."""

from __future__ import annotations

from policy_knowledge.intelligence.role_relevance_schemas import (
    RoleAssessment,
    RoleRelevanceDocument,
    RoleRelevanceResult,
)
from policy_knowledge.model.schemas import PolicyKnowledge
from policy_knowledge.validation.schema_validator import ValidationReport


def _index_knowledge(knowledge: PolicyKnowledge) -> dict[str, dict]:
    """Map artifact_id → {type, source_refs}."""
    index: dict[str, dict] = {}

    def _add(items: list, artifact_type: str) -> None:
        for item in items:
            refs = list(getattr(item, "source_refs", []) or [])
            index[item.id] = {"type": artifact_type, "source_refs": refs}

    _add(knowledge.requirements, "requirement")
    _add(knowledge.roles, "role")
    _add(knowledge.actions, "action")
    _add(knowledge.decisions, "decision")
    _add(knowledge.risks, "risk")
    _add(knowledge.controls, "control")
    _add(knowledge.evidence, "evidence")
    _add(knowledge.findings, "finding")
    return index


def _entity_ids(knowledge: PolicyKnowledge) -> set[str]:
    return set(_index_knowledge(knowledge).keys())


def _filter_assessment(
    assessment: RoleAssessment,
    *,
    known: set[str],
    index: dict[str, dict],
    source_ids: set[str],
) -> tuple[RoleAssessment | None, list[str]]:
    notes: list[str] = []
    if assessment.artifact_id not in known:
        notes.append(f"drop unknown artifact_id {assessment.artifact_id}")
        return None, notes

    expected_type = index[assessment.artifact_id]["type"]
    if assessment.artifact_type != expected_type:
        notes.append(
            f"fix type {assessment.artifact_id}: "
            f"{assessment.artifact_type} -> {expected_type}"
        )
        assessment = assessment.model_copy(update={"artifact_type": expected_type})

    def _keep_ids(ids: list[str], label: str) -> list[str]:
        kept: list[str] = []
        for i in ids:
            if i in known:
                kept.append(i)
            else:
                notes.append(f"drop unknown {label} {i}")
        return kept

    allowed_sources = set(index[assessment.artifact_id]["source_refs"]) | source_ids
    source_refs = []
    for ref in assessment.source_refs:
        if ref in allowed_sources:
            source_refs.append(ref)
        else:
            notes.append(f"drop unknown source_ref {ref} on {assessment.artifact_id}")

    cleaned = assessment.model_copy(
        update={
            "associated_action_ids": _keep_ids(assessment.associated_action_ids, "action"),
            "associated_risk_ids": _keep_ids(assessment.associated_risk_ids, "risk"),
            "associated_control_ids": _keep_ids(assessment.associated_control_ids, "control"),
            "associated_evidence_ids": _keep_ids(assessment.associated_evidence_ids, "evidence"),
            "source_refs": source_refs,
        }
    )
    return cleaned, notes


def filter_role_relevance_result(
    result: RoleRelevanceResult,
    knowledge: PolicyKnowledge,
) -> tuple[RoleRelevanceResult, list[str]]:
    """Drop invented IDs; return cleaned result + notes."""
    index = _index_knowledge(knowledge)
    known = set(index.keys())
    source_ids = {b.id for b in knowledge.source_blocks}
    all_notes: list[str] = []

    def _clean_perspective(assessments: list[RoleAssessment]) -> list[RoleAssessment]:
        out: list[RoleAssessment] = []
        for item in assessments:
            cleaned, notes = _filter_assessment(
                item, known=known, index=index, source_ids=source_ids
            )
            all_notes.extend(notes)
            if cleaned is not None:
                out.append(cleaned)
        return out

    cleaned = RoleRelevanceResult(
        business_owner=result.business_owner.model_copy(
            update={"assessments": _clean_perspective(result.business_owner.assessments)}
        ),
        compliance_officer=result.compliance_officer.model_copy(
            update={"assessments": _clean_perspective(result.compliance_officer.assessments)}
        ),
        policy_owner=result.policy_owner.model_copy(
            update={"assessments": _clean_perspective(result.policy_owner.assessments)}
        ),
    )
    return cleaned, all_notes


def validate_role_relevance(
    doc: RoleRelevanceDocument,
    knowledge: PolicyKnowledge,
) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    if doc.policy_id != knowledge.policy.id:
        errors.append(
            f"policy_id mismatch: role_relevance={doc.policy_id} knowledge={knowledge.policy.id}"
        )
    index = _index_knowledge(knowledge)
    known = set(index.keys())
    source_ids = {b.id for b in knowledge.source_blocks}

    for perspective, body in (doc.perspectives or {}).items():
        for item in body.assessments:
            if item.artifact_id not in known:
                errors.append(f"{perspective}: unknown artifact_id {item.artifact_id}")
                continue
            if item.artifact_type != index[item.artifact_id]["type"]:
                errors.append(
                    f"{perspective}: artifact_type mismatch for {item.artifact_id}"
                )
            for ref in item.source_refs:
                if ref not in source_ids and ref not in index[item.artifact_id]["source_refs"]:
                    errors.append(
                        f"{perspective}: invalid source_ref {ref} on {item.artifact_id}"
                    )
            for label, ids in (
                ("action", item.associated_action_ids),
                ("risk", item.associated_risk_ids),
                ("control", item.associated_control_ids),
                ("evidence", item.associated_evidence_ids),
            ):
                for i in ids:
                    if i not in known:
                        errors.append(
                            f"{perspective}: unknown associated {label} id {i}"
                        )
    if not doc.perspectives:
        warnings.append("no perspectives")
    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)
