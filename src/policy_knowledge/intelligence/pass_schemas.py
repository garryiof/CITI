"""Structured pass response schemas (A–E)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CitedText(BaseModel):
    text: str
    source_refs: list[str] = Field(default_factory=list)


class PassARequirement(BaseModel):
    text: str
    modality: Literal["must", "shall", "should", "may", "unknown"] = "unknown"
    source_refs: list[str] = Field(default_factory=list)


class PassARole(BaseModel):
    name: str
    description: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class PassAResult(BaseModel):
    title: str | None = None
    version: str | None = None
    requirements: list[PassARequirement] = Field(default_factory=list)
    roles: list[PassARole] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PassBAction(BaseModel):
    label: str
    description: str
    actor_role_names: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class PassBDecision(BaseModel):
    question: str
    branches: list[dict] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    ambiguity_flag: bool = False


class PassBResult(BaseModel):
    process_name: str | None = None
    modeling_status: Literal["supported", "unsupported", "partial", "needs_review"] = "needs_review"
    actions: list[PassBAction] = Field(default_factory=list)
    decisions: list[PassBDecision] = Field(default_factory=list)
    flow: list[dict] = Field(default_factory=list)


class PassCRisk(BaseModel):
    name: str
    description: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class PassCControl(BaseModel):
    name: str
    description: str
    owner_role_names: list[str] = Field(default_factory=list)
    frequency: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class PassCEvidence(BaseModel):
    name: str
    description: str | None = None
    related_control_names: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class PassCResult(BaseModel):
    risks: list[PassCRisk] = Field(default_factory=list)
    controls: list[PassCControl] = Field(default_factory=list)
    evidence: list[PassCEvidence] = Field(default_factory=list)


class PassDEdge(BaseModel):
    source_name: str
    target_name: str
    relation_type: str
    derivation: Literal["explicit", "inferred_for_review", "reviewer_confirmed"] = "explicit"
    source_refs: list[str] = Field(default_factory=list)


class PassDResult(BaseModel):
    edges: list[PassDEdge] = Field(default_factory=list)


class PassEFinding(BaseModel):
    severity: str
    category: str
    description: str
    source_refs: list[str] = Field(default_factory=list)
    entity_hints: list[str] = Field(default_factory=list)


class PassEResult(BaseModel):
    findings: list[PassEFinding] = Field(default_factory=list)
