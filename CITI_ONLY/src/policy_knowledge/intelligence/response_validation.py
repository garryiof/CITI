"""Validate LLM structured responses against source citation rules."""

from __future__ import annotations

from dataclasses import dataclass, field

from policy_knowledge.model.schemas import ReviewFinding


@dataclass
class CitationGateResult:
    accepted: list
    rejected: list
    findings: list[ReviewFinding] = field(default_factory=list)


def filter_cited_entities(
    entities: list,
    *,
    available_source_ids: set[str],
    require_source_refs: bool,
    entity_kind: str,
) -> CitationGateResult:
    accepted = []
    rejected = []
    findings: list[ReviewFinding] = []
    for ent in entities:
        refs = list(getattr(ent, "source_refs", []) or [])
        missing = [r for r in refs if r not in available_source_ids]
        if require_source_refs and not refs:
            rejected.append(ent)
            findings.append(
                ReviewFinding(
                    id=f"FIND-MISS-{entity_kind}-{len(findings)+1}",
                    severity="high",
                    category="missing_source_ref",
                    description=f"Rejected {entity_kind} without source_refs: {ent}",
                    entity_ids=[],
                    source_refs=[],
                    disposition="open",
                )
            )
            continue
        if missing:
            findings.append(
                ReviewFinding(
                    id=f"FIND-BADREF-{entity_kind}-{len(findings)+1}",
                    severity="high",
                    category="invalid_source_ref",
                    description=f"{entity_kind} cites unknown source ids: {missing}",
                    entity_ids=[],
                    source_refs=refs,
                    disposition="open",
                )
            )
            if require_source_refs:
                rejected.append(ent)
                continue
        accepted.append(ent)
    return CitationGateResult(accepted=accepted, rejected=rejected, findings=findings)
