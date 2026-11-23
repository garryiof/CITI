"""Provenance helpers for source grounding."""

from __future__ import annotations

from policy_knowledge.model.schemas import PolicyKnowledge, SourceBlock


def index_source_blocks(knowledge: PolicyKnowledge) -> dict[str, SourceBlock]:
    return {block.id: block for block in knowledge.source_blocks}


def missing_source_refs(entity_source_refs: list[str], available: set[str]) -> list[str]:
    return [ref for ref in entity_source_refs if ref not in available]
