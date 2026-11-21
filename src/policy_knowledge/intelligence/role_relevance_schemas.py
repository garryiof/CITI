"""Pydantic schemas for Pass F role-relevance analysis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Relevance = Literal["PRIMARY", "SECONDARY", "NOT_RELEVANT", "UNCERTAIN"]
InterpretationBasis = Literal["explicit", "inferred"]
ArtifactType = Literal[
    "requirement",
    "action",
    "risk",
    "control",
    "evidence",
    "role",
    "decision",
    "finding",
]
PerspectiveKey = Literal["business_owner", "compliance_officer", "policy_owner"]

LensTag = Literal[
    "applicable_requirement",
    "required_action",
    "prohibited_action",
    "operational_risk",
    "deadline_or_approval",
    "control_to_perform",
    "evidence_to_retain",
    "exception_handling",
    "compliance_obligation",
    "testable_requirement",
    "control_verification",
    "evidence_validation",
    "exception_or_breach",
    "test_scenario",
    "policy_objective",
    "risk_coverage",
    "governance_requirement",
    "control_requirement",
    "ownership_accountability",
    "regulatory_dependency",
    "ambiguity_or_gap",
    "change_impact",
]


class RoleAssessment(BaseModel):
    artifact_id: str
    artifact_type: ArtifactType
    relevance: Relevance
    why_relevant: str
    interpretation_basis: InterpretationBasis
    confidence: float | None = None
    source_refs: list[str] = Field(default_factory=list)
    associated_action_ids: list[str] = Field(default_factory=list)
    associated_risk_ids: list[str] = Field(default_factory=list)
    associated_control_ids: list[str] = Field(default_factory=list)
    associated_evidence_ids: list[str] = Field(default_factory=list)
    lens_tags: list[LensTag] = Field(default_factory=list)


class PerspectiveResult(BaseModel):
    assessments: list[RoleAssessment] = Field(default_factory=list)


class RoleRelevanceResult(BaseModel):
    """LLM structured output for Pass F."""

    business_owner: PerspectiveResult = Field(default_factory=PerspectiveResult)
    compliance_officer: PerspectiveResult = Field(default_factory=PerspectiveResult)
    policy_owner: PerspectiveResult = Field(default_factory=PerspectiveResult)


class RoleRelevanceDocument(BaseModel):
    """Persisted role_relevance.json artifact."""

    schema_version: str = "role_relevance-1.0"
    policy_id: str
    generated_at: str
    prompt: dict[str, str] = Field(default_factory=dict)
    llm: dict[str, object] = Field(default_factory=dict)
    perspectives: dict[str, PerspectiveResult] = Field(default_factory=dict)
