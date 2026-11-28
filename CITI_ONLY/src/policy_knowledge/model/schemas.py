"""Pydantic canonical model (master prompt §5)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Modality = Literal["must", "shall", "should", "may", "unknown"]
Derivation = Literal["explicit", "inferred_for_review", "reviewer_confirmed"]
ClassificationOrigin = Literal["source_stated", "normalized", "suggested"]
ReviewStatus = Literal[
    "extracted",
    "needs_review",
    "confirmed",
    "rejected",
    "not_specified",
]
ModelingStatus = Literal[
    "supported",
    "unsupported",
    "partial",
    "needs_review",
]


class Policy(BaseModel):
    id: str
    title: str
    input_path: str
    source_hash: str
    review_status: ReviewStatus
    version: Optional[str] = None
    effective_date: Optional[str] = None


class SourceBlock(BaseModel):
    id: str
    policy_id: str
    section_path: str
    text: str
    block_type: str
    source_locator: str
    sequence: int
    document_hash: str


class Requirement(BaseModel):
    id: str
    text: str
    modality: Modality
    type: str
    source_refs: list[str]
    review_status: ReviewStatus
    confidence: Optional[float] = None


class Role(BaseModel):
    id: str
    name: str
    source_refs: list[str]
    description: Optional[str] = None
    taxonomy_code: Optional[str] = None


class Action(BaseModel):
    id: str
    label: str
    description: str
    actor_role_ids: list[str] = Field(default_factory=list)
    source_refs: list[str]
    preconditions: Optional[list[str]] = None
    outputs: Optional[list[str]] = None


class Process(BaseModel):
    id: str
    name: str
    activities: list[str] = Field(default_factory=list)
    flow_relations: list[dict] = Field(default_factory=list)
    source_refs: list[str]
    modeling_status: ModelingStatus = "needs_review"
    summary: Optional[str] = None
    trigger: Optional[str] = None


class Decision(BaseModel):
    id: str
    question: str
    branches: list[dict] = Field(default_factory=list)
    source_refs: list[str]
    ambiguity_flag: bool = False
    after_action_label: Optional[str] = None


class Risk(BaseModel):
    id: str
    name: str
    source_refs: list[str]
    description: Optional[str] = None
    risk_code: Optional[str] = None
    risk_label: Optional[str] = None
    classification_origin: ClassificationOrigin = "source_stated"


class Control(BaseModel):
    id: str
    name: str
    description: str
    owner_role_ids: list[str] = Field(default_factory=list)
    source_refs: list[str]
    frequency: Optional[str] = None
    type: Optional[str] = None
    classification_origin: ClassificationOrigin = "source_stated"


class Evidence(BaseModel):
    id: str
    name: str
    source_refs: list[str]
    description: Optional[str] = None
    related_control_ids: list[str] = Field(default_factory=list)


class KnowledgeEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation_type: str
    source_refs: list[str]
    derivation: Derivation
    review_status: ReviewStatus
    confidence: Optional[float] = None


class ReviewFinding(BaseModel):
    id: str
    severity: str
    category: str
    description: str
    entity_ids: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    disposition: str = "open"


class PolicyKnowledge(BaseModel):
    policy: Policy
    source_blocks: list[SourceBlock] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    roles: list[Role] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    processes: list[Process] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    controls: list[Control] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    edges: list[KnowledgeEdge] = Field(default_factory=list)
    findings: list[ReviewFinding] = Field(default_factory=list)
    modeling_notes: list[str] = Field(default_factory=list)
