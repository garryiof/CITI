"""Fixture-aligned mock LLM that cites real SourceBlock ids from the prompt."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

from policy_knowledge.intelligence.pass_schemas import (
    PassAResult,
    PassBResult,
    PassCResult,
    PassDResult,
    PassEResult,
    PassWResult,
)
from policy_knowledge.intelligence.role_relevance_schemas import (
    PerspectiveResult,
    RoleAssessment,
    RoleRelevanceResult,
)
from policy_knowledge.model.schemas import PolicyKnowledge


def _user_content(messages: list[dict]) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            return str(msg.get("content", ""))
    return ""


def _blocks_from_messages(messages: list[dict]) -> list[dict[str, str]]:
    user = _user_content(messages)
    marker = "SOURCE_BLOCKS_JSON:"
    if marker not in user:
        return []
    payload = user.split(marker, 1)[1].strip()
    return json.loads(payload)


def _actions_from_messages(messages: list[dict]) -> list[dict]:
    user = _user_content(messages)
    marker = "ACTIONS_JSON:"
    if marker not in user:
        return []
    payload = user.split(marker, 1)[1].strip()
    return json.loads(payload)


def _canonical_from_messages(messages: list[dict]) -> dict:
    user = _user_content(messages)
    marker = "CANONICAL_ARTIFACTS_JSON:"
    if marker not in user:
        return {}
    payload = user.split(marker, 1)[1].strip()
    return json.loads(payload)


def build_synthetic_role_relevance(knowledge: PolicyKnowledge) -> RoleRelevanceResult:
    """Deterministic three-role assessments from canonical entities (mock / fallback)."""
    action_ids = [a.id for a in knowledge.actions]
    risk_ids = [r.id for r in knowledge.risks]
    control_ids = [c.id for c in knowledge.controls]
    evidence_ids = [e.id for e in knowledge.evidence]

    bo: list[RoleAssessment] = []
    co: list[RoleAssessment] = []
    po: list[RoleAssessment] = []

    for req in knowledge.requirements:
        modality = (req.modality or "").lower()
        primary = modality in {"must", "shall"}
        bo.append(
            RoleAssessment(
                artifact_id=req.id,
                artifact_type="requirement",
                relevance="PRIMARY" if primary else "SECONDARY",
                why_relevant="Operational team must satisfy this source-stated obligation.",
                interpretation_basis="explicit",
                confidence=0.85 if primary else 0.7,
                source_refs=list(req.source_refs),
                associated_action_ids=action_ids[:2],
                associated_risk_ids=risk_ids[:1],
                associated_control_ids=control_ids[:1],
                lens_tags=["applicable_requirement", "required_action"],
            )
        )
        co.append(
            RoleAssessment(
                artifact_id=req.id,
                artifact_type="requirement",
                relevance="PRIMARY" if primary else "SECONDARY",
                why_relevant="Compliance must verify adherence to this testable requirement.",
                interpretation_basis="explicit",
                confidence=0.8,
                source_refs=list(req.source_refs),
                associated_control_ids=control_ids[:1],
                associated_evidence_ids=evidence_ids[:1],
                lens_tags=["compliance_obligation", "testable_requirement"],
            )
        )
        po.append(
            RoleAssessment(
                artifact_id=req.id,
                artifact_type="requirement",
                relevance="PRIMARY",
                why_relevant="Policy owner monitors coverage and change impact for this requirement.",
                interpretation_basis="explicit",
                confidence=0.75,
                source_refs=list(req.source_refs),
                associated_risk_ids=risk_ids[:1],
                associated_control_ids=control_ids[:1],
                lens_tags=["policy_objective", "change_impact"],
            )
        )

    for action in knowledge.actions:
        bo.append(
            RoleAssessment(
                artifact_id=action.id,
                artifact_type="action",
                relevance="PRIMARY",
                why_relevant="Business operations must perform or supervise this action.",
                interpretation_basis="explicit",
                confidence=0.8,
                source_refs=list(action.source_refs),
                associated_control_ids=control_ids[:1],
                associated_evidence_ids=evidence_ids[:1],
                lens_tags=["required_action"],
            )
        )
        co.append(
            RoleAssessment(
                artifact_id=action.id,
                artifact_type="action",
                relevance="SECONDARY",
                why_relevant="Action provides a compliance testing hook for related controls.",
                interpretation_basis="inferred",
                confidence=0.6,
                source_refs=list(action.source_refs),
                associated_control_ids=control_ids[:1],
                lens_tags=["test_scenario"],
            )
        )

    for risk in knowledge.risks:
        for perspective, tags, why in (
            (
                bo,
                ["operational_risk"],
                "Operational exposure the business must manage.",
            ),
            (
                co,
                ["compliance_obligation"],
                "Risk within the compliance assessment universe.",
            ),
            (
                po,
                ["risk_coverage"],
                "Policy owner must ensure this risk is covered by controls.",
            ),
        ):
            perspective.append(
                RoleAssessment(
                    artifact_id=risk.id,
                    artifact_type="risk",
                    relevance="PRIMARY",
                    why_relevant=why,
                    interpretation_basis="explicit",
                    confidence=0.8,
                    source_refs=list(risk.source_refs),
                    associated_control_ids=control_ids[:1],
                    lens_tags=tags,  # type: ignore[arg-type]
                )
            )

    for control in knowledge.controls:
        bo.append(
            RoleAssessment(
                artifact_id=control.id,
                artifact_type="control",
                relevance="PRIMARY",
                why_relevant="Business must perform or support this control activity.",
                interpretation_basis="explicit",
                confidence=0.8,
                source_refs=list(control.source_refs),
                associated_evidence_ids=evidence_ids[:1],
                associated_risk_ids=risk_ids[:1],
                lens_tags=["control_to_perform"],
            )
        )
        co.append(
            RoleAssessment(
                artifact_id=control.id,
                artifact_type="control",
                relevance="PRIMARY",
                why_relevant="Compliance must verify this control operates as designed.",
                interpretation_basis="explicit",
                confidence=0.85,
                source_refs=list(control.source_refs),
                associated_evidence_ids=evidence_ids[:1],
                associated_risk_ids=risk_ids[:1],
                lens_tags=["control_verification"],
            )
        )
        po.append(
            RoleAssessment(
                artifact_id=control.id,
                artifact_type="control",
                relevance="PRIMARY",
                why_relevant="Policy owner accounts for control requirements and ownership.",
                interpretation_basis="explicit",
                confidence=0.8,
                source_refs=list(control.source_refs),
                associated_risk_ids=risk_ids[:1],
                lens_tags=["control_requirement", "ownership_accountability"],
            )
        )

    for evidence in knowledge.evidence:
        bo.append(
            RoleAssessment(
                artifact_id=evidence.id,
                artifact_type="evidence",
                relevance="PRIMARY",
                why_relevant="Operations must retain this evidence of control performance.",
                interpretation_basis="explicit",
                confidence=0.8,
                source_refs=list(evidence.source_refs),
                associated_control_ids=list(evidence.related_control_ids)[:1] or control_ids[:1],
                lens_tags=["evidence_to_retain"],
            )
        )
        co.append(
            RoleAssessment(
                artifact_id=evidence.id,
                artifact_type="evidence",
                relevance="PRIMARY",
                why_relevant="Compliance validates that retained evidence supports control testing.",
                interpretation_basis="explicit",
                confidence=0.85,
                source_refs=list(evidence.source_refs),
                associated_control_ids=list(evidence.related_control_ids)[:1] or control_ids[:1],
                lens_tags=["evidence_validation"],
            )
        )

    for finding in knowledge.findings:
        po.append(
            RoleAssessment(
                artifact_id=finding.id,
                artifact_type="finding",
                relevance="PRIMARY",
                why_relevant="Ambiguity or gap requiring policy owner attention.",
                interpretation_basis="inferred",
                confidence=0.7,
                source_refs=list(finding.source_refs),
                lens_tags=["ambiguity_or_gap"],
            )
        )
        co.append(
            RoleAssessment(
                artifact_id=finding.id,
                artifact_type="finding",
                relevance="SECONDARY",
                why_relevant="Potential exception or breach scenario for compliance review.",
                interpretation_basis="inferred",
                confidence=0.65,
                source_refs=list(finding.source_refs),
                lens_tags=["exception_or_breach", "test_scenario"],
            )
        )

    return RoleRelevanceResult(
        business_owner=PerspectiveResult(assessments=bo),
        compliance_officer=PerspectiveResult(assessments=co),
        policy_owner=PerspectiveResult(assessments=po),
    )


def _role_relevance_from_canonical(payload: dict) -> RoleRelevanceResult:
    """Build RoleRelevanceResult from Pass F user payload without full PolicyKnowledge."""
    from types import SimpleNamespace

    knowledge = SimpleNamespace(
        requirements=[SimpleNamespace(**r) for r in payload.get("requirements") or []],
        roles=[SimpleNamespace(**r) for r in payload.get("roles") or []],
        actions=[
            SimpleNamespace(**{**a, "actor_role_ids": a.get("actor_role_ids") or []})
            for a in payload.get("actions") or []
        ],
        decisions=[SimpleNamespace(**d) for d in payload.get("decisions") or []],
        risks=[SimpleNamespace(**r) for r in payload.get("risks") or []],
        controls=[
            SimpleNamespace(**{**c, "owner_role_ids": c.get("owner_role_ids") or []})
            for c in payload.get("controls") or []
        ],
        evidence=[
            SimpleNamespace(
                **{**e, "related_control_ids": e.get("related_control_ids") or []}
            )
            for e in payload.get("evidence") or []
        ],
        findings=[
            SimpleNamespace(**{**f, "entity_ids": f.get("entity_ids") or []})
            for f in payload.get("findings") or []
        ],
        edges=[],
        policy=SimpleNamespace(**(payload.get("policy") or {"id": "", "title": ""})),
        source_blocks=[],
    )
    return build_synthetic_role_relevance(knowledge)  # type: ignore[arg-type]


def _find_ref(blocks: list[dict[str, str]], *needles: str) -> list[str]:
    refs: list[str] = []
    for block in blocks:
        text = block.get("text", "").lower()
        if all(n.lower() in text for n in needles):
            refs.append(block["id"])
    if refs:
        return refs[:1]
    # fallback: first block containing any needle
    for block in blocks:
        text = block.get("text", "").lower()
        if any(n.lower() in text for n in needles):
            return [block["id"]]
    return [blocks[0]["id"]] if blocks else []


class SyntheticMockLLM:
    """Deterministic CREATE/PARSE stand-in for synthetic policies."""

    def __init__(self, mode: str = "procedural", inject_uncited: bool = False) -> None:
        self.mode = mode
        self.inject_uncited = inject_uncited

    def generate_text(self, messages: list[dict], **kwargs: Any) -> str:
        return "{}"

    def generate_narrative(self, messages: list[dict], **kwargs: Any) -> str:
        return "Synthetic narrative for review only."

    def parse_structured(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        if schema is RoleRelevanceResult:
            payload = _canonical_from_messages(messages)
            if payload:
                return _role_relevance_from_canonical(payload)
            return RoleRelevanceResult()
        if schema is PassWResult:
            return self._pass_w(_actions_from_messages(messages))
        blocks = _blocks_from_messages(messages)
        if schema is PassAResult:
            return self._pass_a(blocks)
        if schema is PassBResult:
            return self._pass_b(blocks)
        if schema is PassCResult:
            return self._pass_c(blocks)
        if schema is PassDResult:
            return self._pass_d(blocks)
        if schema is PassEResult:
            return self._pass_e(blocks)
        raise TypeError(f"Unsupported schema for SyntheticMockLLM: {schema}")

    def _pass_a(self, blocks: list[dict[str, str]]) -> PassAResult:
        if self.mode == "nonprocedural":
            data = {
                "title": "Synthetic Principles Policy",
                "requirements": [
                    {
                        "text": "Teams should treat customers fairly and document material judgments.",
                        "modality": "should",
                        "source_refs": _find_ref(blocks, "fairly"),
                    }
                ],
                "roles": [],
            }
            return PassAResult.model_validate(data)

        reqs = []
        for modality, needle in [
            ("must", "must escalate"),
            ("shall", "shall document"),
            ("should", "should retain"),
        ]:
            refs = _find_ref(blocks, needle.split()[0], needle.split()[1]) if " " in needle else _find_ref(blocks, needle)
            # simpler needle
            refs = _find_ref(blocks, needle)
            text = next((b["text"] for b in blocks if needle in b["text"].lower()), needle)
            item = {"text": text, "modality": modality, "source_refs": refs}
            if self.inject_uncited and modality == "should":
                item["source_refs"] = []
            reqs.append(item)

        roles = [
            {"name": "Policy Owner", "source_refs": _find_ref(blocks, "policy owner")},
            {"name": "Process Performer", "description": "Analyst", "source_refs": _find_ref(blocks, "analyst")},
            {"name": "Approver", "source_refs": _find_ref(blocks, "approver")},
        ]
        return PassAResult.model_validate(
            {
                "title": "Synthetic Escalation Policy",
                "version": "1.0",
                "requirements": reqs,
                "roles": roles,
            }
        )

    def _pass_b(self, blocks: list[dict[str, str]]) -> PassBResult:
        if self.mode == "nonprocedural":
            return PassBResult.model_validate(
                {
                    "process_name": "No supported process",
                    "modeling_status": "unsupported",
                    "actions": [],
                    "decisions": [],
                    "flow": [],
                }
            )
        actions = [
            {
                "label": "Identify exception",
                "description": "Identify the exception and capture transaction identifiers.",
                "actor_role_names": ["Process Performer"],
                "source_refs": _find_ref(blocks, "identify the exception"),
            },
            {
                "label": "Route high-value exception",
                "description": "If amount exceeds 10,000 USD, route to Approver.",
                "actor_role_names": ["Process Performer"],
                "source_refs": _find_ref(blocks, "10,000"),
            },
            {
                "label": "Record decision",
                "description": "Approver records approve or reject.",
                "actor_role_names": ["Approver"],
                "source_refs": _find_ref(blocks, "approve or reject"),
            },
            {
                "label": "Retain evidence",
                "description": "Retain control evidence in the case file.",
                "actor_role_names": ["Process Performer"],
                "source_refs": _find_ref(blocks, "retain control evidence"),
            },
        ]
        decisions = [
            {
                "question": "Does exception amount exceed 10,000 USD?",
                "branches": [
                    {"label": "yes", "target": "Record decision"},
                    {"label": "no", "target": "Retain evidence"},
                ],
                "source_refs": _find_ref(blocks, "10,000"),
                "ambiguity_flag": False,
            }
        ]
        return PassBResult.model_validate(
            {
                "process_name": "Exception escalation",
                "modeling_status": "supported",
                "actions": actions,
                "decisions": decisions,
                "flow": [
                    {"from": "Identify exception", "to": "Route high-value exception"},
                    {"from": "Route high-value exception", "to": "Record decision"},
                    {"from": "Record decision", "to": "Retain evidence"},
                ],
            }
        )

    def _pass_w(self, actions: list[dict]) -> PassWResult:
        labels = [a["label"] for a in actions if a.get("label")]
        if len(labels) < 2:
            return PassWResult()
        return PassWResult.model_validate(
            {
                "workflows": [
                    {
                        "title": "Escalate an exception",
                        "summary": "Identify, route and decide on a policy exception.",
                        "trigger": "An exception is identified.",
                        "action_labels": labels[:-1],
                    },
                    {
                        "title": "Retain control evidence",
                        "summary": "Keep evidence of the control outcome.",
                        "trigger": "A decision is recorded.",
                        "action_labels": labels[-1:],
                    },
                ]
            }
        )

    def _pass_c(self, blocks: list[dict[str, str]]) -> PassCResult:
        if self.mode == "nonprocedural":
            return PassCResult()
        return PassCResult.model_validate(
            {
                "risks": [
                    {
                        "name": "Operational Risk — delayed escalation",
                        "description": "Delayed escalation may leave synthetic exposure unmanaged.",
                        "source_refs": _find_ref(blocks, "operational risk"),
                    }
                ],
                "controls": [
                    {
                        "name": "Dual review",
                        "description": "Dual review of high-value exceptions",
                        "owner_role_names": ["Approver"],
                        "frequency": "each occurrence",
                        "source_refs": _find_ref(blocks, "dual review"),
                    }
                ],
                "evidence": [
                    {
                        "name": "Escalation ticket and approval record",
                        "related_control_names": ["Dual review"],
                        "source_refs": _find_ref(blocks, "escalation ticket"),
                    }
                ],
            }
        )

    def _pass_d(self, blocks: list[dict[str, str]]) -> PassDResult:
        if self.mode == "nonprocedural":
            return PassDResult(
                edges=[
                    {
                        "source_name": "Teams should treat customers fairly and document material judgments.",
                        "target_name": _find_ref(blocks, "fairly")[0] if blocks else "SRC",
                        "relation_type": "ENTITY_GROUNDED_IN_SOURCE",
                        "derivation": "explicit",
                        "source_refs": _find_ref(blocks, "fairly"),
                    }
                ]
            )
        edges = [
            {
                "source_name": "Analysts must escalate exceptions within 1 business day.",
                "target_name": "Identify exception",
                "relation_type": "REQUIREMENT_REQUIRES_ACTION",
                "derivation": "explicit",
                "source_refs": _find_ref(blocks, "must escalate"),
            },
            {
                "source_name": "Process Performer",
                "target_name": "Identify exception",
                "relation_type": "ROLE_PERFORMS_ACTION",
                "derivation": "explicit",
                "source_refs": _find_ref(blocks, "analyst"),
            },
            {
                "source_name": "Approver",
                "target_name": "Dual review",
                "relation_type": "ROLE_OWNS_CONTROL",
                "derivation": "explicit",
                "source_refs": _find_ref(blocks, "control owner is the approver")
                or _find_ref(blocks, "approver"),
            },
            {
                "source_name": "Dual review",
                "target_name": "Operational Risk — delayed escalation",
                "relation_type": "CONTROL_MITIGATES_RISK",
                "derivation": "inferred_for_review",
                "source_refs": _find_ref(blocks, "dual review"),
            },
            {
                "source_name": "Identify exception",
                "target_name": "Route high-value exception",
                "relation_type": "ACTION_PRECEDES_ACTION",
                "derivation": "explicit",
                "source_refs": _find_ref(blocks, "identify the exception"),
            },
        ]
        return PassDResult.model_validate({"edges": edges})

    def _pass_e(self, blocks: list[dict[str, str]]) -> PassEResult:
        findings = [
            {
                "severity": "medium",
                "category": "ambiguity",
                "description": "Unclear whether weekend hours count toward the escalation SLA.",
                "source_refs": _find_ref(blocks, "weekend"),
            }
        ]
        return PassEResult.model_validate({"findings": findings})
