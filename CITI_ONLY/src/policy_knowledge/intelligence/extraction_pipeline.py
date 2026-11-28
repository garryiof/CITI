"""Multi-pass extraction orchestration (Passes A–E)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from policy_knowledge.governance.taxonomy_mapper import (
    default_taxonomy_dir,
    load_entries,
    resolve_match,
)
from policy_knowledge.ingestion.chunker import chunk_blocks
from policy_knowledge.intelligence.guardrail_client import LLMAdapter, build_messages
from policy_knowledge.intelligence.pass_schemas import (
    PassAResult,
    PassBResult,
    PassCResult,
    PassDResult,
    PassEResult,
    PassWResult,
)
from policy_knowledge.intelligence.prompt_loader import load_prompt
from policy_knowledge.intelligence.reconciliation import reconcile_knowledge
from policy_knowledge.intelligence.response_validation import filter_cited_entities
from policy_knowledge.model.entity_ids import stable_edge_id, stable_entity_id
from policy_knowledge.model.schemas import (
    Action,
    Control,
    Decision,
    Evidence,
    KnowledgeEdge,
    Policy,
    PolicyKnowledge,
    Process,
    Requirement,
    ReviewFinding,
    Risk,
    Role,
    SourceBlock,
)


def _blocks_payload(blocks: list[SourceBlock]) -> str:
    payload = [{"id": b.id, "text": b.text, "section_path": b.section_path} for b in blocks]
    return "SOURCE_BLOCKS_JSON:\n" + json.dumps(payload, ensure_ascii=False)


def _pass_messages(
    pass_key: str,
    source_blocks_payload: str,
    system_suffix: str = "",
) -> list[dict[str, str]]:
    system = load_prompt(f"{pass_key}.system").text
    if system_suffix:
        system = f"{system.rstrip()}\n\n{system_suffix}"
    user = load_prompt(
        f"{pass_key}.user",
        variables={"source_blocks_payload": source_blocks_payload},
    ).text.rstrip("\n")
    return build_messages(system, user)


_RISK_TAXONOMY_RULES = (
    "Risk taxonomy: each risk must carry taxonomy_candidate_id set to the id of the best-fitting entry "
    "in RISK_TAXONOMY_JSON below, or null when no entry fits. Never invent an id. Keep each risk name "
    "as the policy wording; do not rewrite it to a taxonomy label."
)


def _taxonomy_system_block(marker: str, entries: list[dict[str, Any]]) -> str:
    compact = [
        {
            "id": e.get("id"),
            "label": e.get("label"),
            "definition": e.get("definition"),
            "aliases": e.get("aliases") or [],
        }
        for e in entries
    ]
    return f"{_RISK_TAXONOMY_RULES}\n\n{marker}:\n{json.dumps(compact, ensure_ascii=False)}"


def _extend_unique(target: list[str], extra: list[str]) -> None:
    for item in extra:
        if item and item not in target:
            target.append(item)


def _chunk_block_groups(blocks: list[SourceBlock], max_chunk_chars: int) -> list[list[SourceBlock]]:
    if not blocks:
        return [[]]
    chunks = chunk_blocks(blocks, max_chars=max(1, int(max_chunk_chars)), overlap=200)
    if len(chunks) <= 1:
        return [blocks]
    by_id = {b.id: b for b in blocks}
    groups: list[list[SourceBlock]] = []
    for chunk in chunks:
        ids = chunk.metadata.get("source_block_ids") or []
        group = [by_id[bid] for bid in ids if bid in by_id]
        if group:
            groups.append(group)
    return groups or [blocks]


def _merge_pass_a(results: list[PassAResult]) -> PassAResult:
    if len(results) == 1:
        return results[0]
    title: Optional[str] = None
    version: Optional[str] = None
    reqs: list[Any] = []
    req_by_key: dict[str, Any] = {}
    roles: list[Any] = []
    role_by_key: dict[str, Any] = {}
    notes: list[str] = []
    for res in results:
        if not title and res.title:
            title = res.title
        if not version and res.version:
            version = res.version
        for r in res.requirements:
            key = r.text.strip().lower()
            if key in req_by_key:
                _extend_unique(req_by_key[key].source_refs, r.source_refs)
            else:
                copy = r.model_copy(deep=True)
                req_by_key[key] = copy
                reqs.append(copy)
        for role in res.roles:
            key = role.name.strip().lower()
            if key in role_by_key:
                _extend_unique(role_by_key[key].source_refs, role.source_refs)
                if not role_by_key[key].description and role.description:
                    role_by_key[key].description = role.description
            else:
                copy = role.model_copy(deep=True)
                role_by_key[key] = copy
                roles.append(copy)
        _extend_unique(notes, res.notes)
    return PassAResult(title=title, version=version, requirements=reqs, roles=roles, notes=notes)


_STATUS_PRIORITY = {"supported": 0, "partial": 1, "needs_review": 2, "unsupported": 3}


def _merge_pass_b(results: list[PassBResult]) -> PassBResult:
    if len(results) == 1:
        return results[0]
    process_name: Optional[str] = None
    status = "unsupported"
    actions: list[Any] = []
    action_by_key: dict[str, Any] = {}
    decisions: list[Any] = []
    decision_by_key: dict[str, Any] = {}
    flow: list[dict] = []
    seen_flow: set[tuple[str, str]] = set()
    for res in results:
        if not process_name and res.process_name:
            process_name = res.process_name
        if _STATUS_PRIORITY.get(res.modeling_status, 9) < _STATUS_PRIORITY.get(status, 9):
            status = res.modeling_status
        for act in res.actions:
            key = act.label.strip().lower()
            if key in action_by_key:
                existing = action_by_key[key]
                _extend_unique(existing.source_refs, act.source_refs)
                _extend_unique(existing.actor_role_names, act.actor_role_names)
                if len(act.description or "") > len(existing.description or ""):
                    existing.description = act.description
            else:
                copy = act.model_copy(deep=True)
                action_by_key[key] = copy
                actions.append(copy)
        for dec in res.decisions:
            key = dec.question.strip().lower()
            if key in decision_by_key:
                existing = decision_by_key[key]
                _extend_unique(existing.source_refs, dec.source_refs)
                if not existing.branches and dec.branches:
                    existing.branches = list(dec.branches)
                if not existing.after_action_label and dec.after_action_label:
                    existing.after_action_label = dec.after_action_label
            else:
                copy = dec.model_copy(deep=True)
                decision_by_key[key] = copy
                decisions.append(copy)
        for item in res.flow:
            if not item:
                continue
            src = str(item.get("from") or "").strip()
            tgt = str(item.get("to") or "").strip()
            if not src or not tgt:
                continue
            pair = (src.lower(), tgt.lower())
            if pair not in seen_flow:
                seen_flow.add(pair)
                flow.append({"from": src, "to": tgt})
    if actions and status == "unsupported":
        status = "supported"
    return PassBResult(
        process_name=process_name,
        modeling_status=status,  # type: ignore[arg-type]
        actions=actions,
        decisions=decisions,
        flow=flow,
    )


def _merge_pass_c(results: list[PassCResult]) -> PassCResult:
    if len(results) == 1:
        return results[0]
    risks: list[Any] = []
    risk_by_key: dict[str, Any] = {}
    controls: list[Any] = []
    ctl_by_key: dict[str, Any] = {}
    evidence: list[Any] = []
    ev_by_key: dict[str, Any] = {}
    for res in results:
        for r in res.risks:
            key = r.name.strip().lower()
            if key in risk_by_key:
                existing = risk_by_key[key]
                _extend_unique(existing.source_refs, r.source_refs)
                if not existing.taxonomy_candidate_id and r.taxonomy_candidate_id:
                    existing.taxonomy_candidate_id = r.taxonomy_candidate_id
                if not existing.description and r.description:
                    existing.description = r.description
            else:
                copy = r.model_copy(deep=True)
                risk_by_key[key] = copy
                risks.append(copy)
        for c in res.controls:
            key = c.name.strip().lower()
            if key in ctl_by_key:
                existing = ctl_by_key[key]
                _extend_unique(existing.source_refs, c.source_refs)
                _extend_unique(existing.owner_role_names, c.owner_role_names)
                if not existing.frequency and c.frequency:
                    existing.frequency = c.frequency
            else:
                copy = c.model_copy(deep=True)
                ctl_by_key[key] = copy
                controls.append(copy)
        for e in res.evidence:
            key = e.name.strip().lower()
            if key in ev_by_key:
                existing = ev_by_key[key]
                _extend_unique(existing.source_refs, e.source_refs)
                _extend_unique(existing.related_control_names, e.related_control_names)
                if not existing.description and e.description:
                    existing.description = e.description
            else:
                copy = e.model_copy(deep=True)
                ev_by_key[key] = copy
                evidence.append(copy)
    return PassCResult(risks=risks, controls=controls, evidence=evidence)


def _merge_pass_d(results: list[PassDResult]) -> PassDResult:
    if len(results) == 1:
        return results[0]
    edges: list[Any] = []
    edge_by_key: dict[tuple[str, str, str], Any] = {}
    for res in results:
        for edge in res.edges:
            key = (
                edge.source_name.strip().lower(),
                edge.relation_type.strip().upper(),
                edge.target_name.strip().lower(),
            )
            if key in edge_by_key:
                _extend_unique(edge_by_key[key].source_refs, edge.source_refs)
            else:
                copy = edge.model_copy(deep=True)
                edge_by_key[key] = copy
                edges.append(copy)
    return PassDResult(edges=edges)


def _merge_pass_e(results: list[PassEResult]) -> PassEResult:
    if len(results) == 1:
        return results[0]
    findings: list[Any] = []
    finding_by_key: dict[tuple[str, str], Any] = {}
    for res in results:
        for f in res.findings:
            key = (f.category.strip().lower(), f.description.strip().lower())
            if key in finding_by_key:
                _extend_unique(finding_by_key[key].source_refs, f.source_refs)
                _extend_unique(finding_by_key[key].entity_hints, f.entity_hints)
            else:
                copy = f.model_copy(deep=True)
                finding_by_key[key] = copy
                findings.append(copy)
    return PassEResult(findings=findings)


def _group_workflows(
    llm: LLMAdapter,
    *,
    policy_title: str,
    actions: list[Action],
    role_names: dict[str, str],
    findings: list[ReviewFinding],
) -> list[Process]:
    """Pass W: group resolved actions into named workflows (empty list on failure)."""
    if len(actions) < 2:
        return []
    payload = [
        {
            "label": a.label,
            "description": a.description,
            "actors": [role_names.get(r, r) for r in a.actor_role_ids],
            "source_refs": a.source_refs,
        }
        for a in actions
    ]
    system = load_prompt("pass_w.system").text
    user = load_prompt(
        "pass_w.user",
        variables={
            "policy_title": policy_title,
            "actions_payload": json.dumps(payload, ensure_ascii=False),
        },
    ).text.rstrip("\n")
    try:
        result = llm.parse_structured(build_messages(system, user), PassWResult)
    except Exception as exc:  # noqa: BLE001 — grouping is optional; whole-policy workflow remains
        findings.append(
            ReviewFinding(
                id=f"FIND-WORKFLOW-{len(findings)+1}",
                severity="low",
                category="workflow_grouping_failed",
                description=f"Pass W failed; offline pack shows the whole-policy workflow only: {exc}",
                disposition="open",
            )
        )
        return []

    by_label = {a.label.strip().lower(): a for a in actions}
    processes: list[Process] = []
    seen: set[str] = set()
    for wf in result.workflows:
        members: list[Action] = []
        for label in wf.action_labels:
            action = by_label.get(label.strip().lower())
            if action is not None and action not in members:
                members.append(action)
        if not members:
            continue
        process_id = stable_entity_id("process", wf.title, members[0].id)
        if process_id in seen:
            continue
        seen.add(process_id)
        refs: list[str] = []
        for action in members:
            refs.extend(r for r in action.source_refs if r not in refs)
        processes.append(
            Process(
                id=process_id,
                name=wf.title,
                activities=[a.id for a in members],
                flow_relations=[
                    {"from": members[i].label, "to": members[i + 1].label}
                    for i in range(len(members) - 1)
                ],
                source_refs=refs,
                modeling_status="supported",
                summary=wf.summary,
                trigger=wf.trigger,
            )
        )

    if processes:
        covered_ids = {aid for proc in processes for aid in proc.activities}
        uncovered = [a for a in actions if a.id not in covered_ids]
        if uncovered:
            refs = []
            for action in uncovered:
                refs.extend(r for r in action.source_refs if r not in refs)
            extra_title = "Additional policy obligations and procedures"
            extra_id = stable_entity_id("process", extra_title, uncovered[0].id)
            if extra_id not in seen:
                processes.append(
                    Process(
                        id=extra_id,
                        name=extra_title,
                        activities=[a.id for a in uncovered],
                        flow_relations=[
                            {"from": uncovered[i].label, "to": uncovered[i + 1].label}
                            for i in range(len(uncovered) - 1)
                        ],
                        source_refs=refs,
                        modeling_status="supported",
                        summary="Remaining obligations and compliance steps extracted from the policy.",
                        trigger="When additional policy obligations apply.",
                    )
                )
    return processes


def extract_policy(
    blocks: list[SourceBlock],
    llm: LLMAdapter,
    *,
    policy_id: str,
    title: str,
    input_path: str = "",
    source_hash: Optional[str] = None,
    require_source_refs: bool = True,
    risk_taxonomy_path: Optional[Path] = None,
    max_chunk_chars: int = 12000,
) -> PolicyKnowledge:
    available = {b.id for b in blocks}
    doc_hash = source_hash or (blocks[0].document_hash if blocks else "")
    block_groups = _chunk_block_groups(blocks, max_chunk_chars=max_chunk_chars)
    chunk_payloads = [_blocks_payload(group) for group in block_groups]

    pass_a = _merge_pass_a(
        [llm.parse_structured(_pass_messages("pass_a", payload), PassAResult) for payload in chunk_payloads]
    )
    pass_b = _merge_pass_b(
        [llm.parse_structured(_pass_messages("pass_b", payload), PassBResult) for payload in chunk_payloads]
    )
    risk_taxonomy_path = Path(risk_taxonomy_path) if risk_taxonomy_path else default_taxonomy_dir() / "risk_taxonomy.yaml"
    risk_entries = load_entries(risk_taxonomy_path, "risks")
    taxonomy_suffix = _taxonomy_system_block("RISK_TAXONOMY_JSON", risk_entries)
    pass_c = _merge_pass_c(
        [
            llm.parse_structured(
                _pass_messages("pass_c", payload, system_suffix=taxonomy_suffix),
                PassCResult,
            )
            for payload in chunk_payloads
        ]
    )
    pass_d = _merge_pass_d(
        [llm.parse_structured(_pass_messages("pass_d", payload), PassDResult) for payload in chunk_payloads]
    )
    pass_e = _merge_pass_e(
        [llm.parse_structured(_pass_messages("pass_e", payload), PassEResult) for payload in chunk_payloads]
    )

    findings: list[ReviewFinding] = []

    if not pass_b.actions and pass_b.modeling_status in ("supported", "partial"):
        findings.append(
            ReviewFinding(
                id="FIND-PASSB-EMPTY-1",
                severity="high",
                category="empty_pass_b_actions",
                description=(
                    f"Pass B reported modeling_status={pass_b.modeling_status} but returned no actions; "
                    "no workflow can be built. Re-run or review the procedure in the source."
                ),
                source_refs=[],
                disposition="open",
            )
        )

    req_gate = filter_cited_entities(
        pass_a.requirements,
        available_source_ids=available,
        require_source_refs=require_source_refs,
        entity_kind="requirement",
    )
    findings.extend(req_gate.findings)
    role_gate = filter_cited_entities(
        pass_a.roles,
        available_source_ids=available,
        require_source_refs=require_source_refs,
        entity_kind="role",
    )
    findings.extend(role_gate.findings)
    action_gate = filter_cited_entities(
        pass_b.actions,
        available_source_ids=available,
        require_source_refs=require_source_refs,
        entity_kind="action",
    )
    findings.extend(action_gate.findings)

    roles: list[Role] = []
    role_by_name: dict[str, Role] = {}
    for raw in role_gate.accepted:
        primary = raw.source_refs[0] if raw.source_refs else "NONE"
        role = Role(
            id=stable_entity_id("role", raw.name, primary),
            name=raw.name,
            description=raw.description,
            source_refs=list(raw.source_refs),
        )
        roles.append(role)
        role_by_name[raw.name.lower()] = role

    requirements: list[Requirement] = []
    req_by_text: dict[str, Requirement] = {}
    for raw in req_gate.accepted:
        primary = raw.source_refs[0]
        req = Requirement(
            id=stable_entity_id("requirement", raw.text, primary),
            text=raw.text,
            modality=raw.modality,
            type="obligation",
            source_refs=list(raw.source_refs),
            review_status="extracted",
        )
        requirements.append(req)
        req_by_text[raw.text.strip().lower()] = req

    actions: list[Action] = []
    action_by_label: dict[str, Action] = {}
    for raw in action_gate.accepted:
        primary = raw.source_refs[0]
        actor_ids = []
        for name in raw.actor_role_names:
            role = role_by_name.get(name.lower())
            if role:
                actor_ids.append(role.id)
        action = Action(
            id=stable_entity_id("action", raw.label, primary),
            label=raw.label,
            description=raw.description,
            actor_role_ids=actor_ids,
            source_refs=list(raw.source_refs),
        )
        actions.append(action)
        action_by_label[raw.label.lower()] = action

    decisions: list[Decision] = []
    for raw in pass_b.decisions:
        if require_source_refs and not raw.source_refs:
            findings.append(
                ReviewFinding(
                    id=f"FIND-MISS-decision-{len(findings)+1}",
                    severity="high",
                    category="missing_source_ref",
                    description=f"Rejected decision without source_refs: {raw.question}",
                    disposition="open",
                )
            )
            continue
        primary = raw.source_refs[0] if raw.source_refs else "NONE"
        decisions.append(
            Decision(
                id=stable_entity_id("decision", raw.question, primary),
                question=raw.question,
                branches=list(raw.branches),
                source_refs=list(raw.source_refs),
                ambiguity_flag=raw.ambiguity_flag,
                after_action_label=raw.after_action_label,
            )
        )

    risks: list[Risk] = []
    risk_by_name: dict[str, Risk] = {}
    risk_gate = filter_cited_entities(
        pass_c.risks,
        available_source_ids=available,
        require_source_refs=require_source_refs,
        entity_kind="risk",
    )
    findings.extend(risk_gate.findings)
    for raw in risk_gate.accepted:
        primary = raw.source_refs[0]
        match = resolve_match(raw.name, raw.taxonomy_candidate_id, risk_taxonomy_path, "risks")
        origin = {"exact": "normalized", "alias": "normalized", "llm_suggested": "suggested"}.get(
            match.status, "source_stated"
        )
        risk = Risk(
            id=stable_entity_id("risk", raw.name, primary),
            name=raw.name,
            description=raw.description,
            source_refs=list(raw.source_refs),
            risk_code=match.code if match.status != "unmapped" else None,
            risk_label=match.label if match.status != "unmapped" else None,
            classification_origin=origin,
        )
        if match.status == "unmapped":
            findings.append(
                ReviewFinding(
                    id=f"FIND-RISK-TAX-{len(findings)+1}",
                    severity="low",
                    category="unmapped_risk",
                    description=f"Risk '{raw.name}' has no CITI risk taxonomy match; review manually.",
                    entity_ids=[risk.id],
                    source_refs=list(raw.source_refs),
                    disposition="open",
                )
            )
        risks.append(risk)
        risk_by_name[raw.name.lower()] = risk

    controls: list[Control] = []
    control_by_name: dict[str, Control] = {}
    ctl_gate = filter_cited_entities(
        pass_c.controls,
        available_source_ids=available,
        require_source_refs=require_source_refs,
        entity_kind="control",
    )
    findings.extend(ctl_gate.findings)
    for raw in ctl_gate.accepted:
        primary = raw.source_refs[0]
        owners = []
        for name in raw.owner_role_names:
            role = role_by_name.get(name.lower())
            if role:
                owners.append(role.id)
        control = Control(
            id=stable_entity_id("control", raw.name, primary),
            name=raw.name,
            description=raw.description,
            owner_role_ids=owners,
            frequency=raw.frequency,
            source_refs=list(raw.source_refs),
            classification_origin="source_stated",
        )
        controls.append(control)
        control_by_name[raw.name.lower()] = control

    evidence_items: list[Evidence] = []
    evid_gate = filter_cited_entities(
        pass_c.evidence,
        available_source_ids=available,
        require_source_refs=require_source_refs,
        entity_kind="evidence",
    )
    findings.extend(evid_gate.findings)
    for raw in evid_gate.accepted:
        primary = raw.source_refs[0]
        related = [
            control_by_name[n.lower()].id
            for n in raw.related_control_names
            if n.lower() in control_by_name
        ]
        evidence_items.append(
            Evidence(
                id=stable_entity_id("evidence", raw.name, primary),
                name=raw.name,
                description=raw.description,
                related_control_ids=related,
                source_refs=list(raw.source_refs),
            )
        )

    name_index: dict[str, str] = {}
    for req in requirements:
        name_index[req.text.strip().lower()] = req.id
    for role in roles:
        name_index[role.name.strip().lower()] = role.id
    for action in actions:
        name_index[action.label.strip().lower()] = action.id
    for risk in risks:
        name_index[risk.name.strip().lower()] = risk.id
    for control in controls:
        name_index[control.name.strip().lower()] = control.id
    for evid in evidence_items:
        name_index[evid.name.strip().lower()] = evid.id
    for block in blocks:
        name_index[block.id.lower()] = block.id

    edges: list[KnowledgeEdge] = []
    for raw in pass_d.edges:
        src = name_index.get(raw.source_name.strip().lower())
        tgt = name_index.get(raw.target_name.strip().lower())
        if not src or not tgt:
            findings.append(
                ReviewFinding(
                    id=f"FIND-EDGE-{len(findings)+1}",
                    severity="medium",
                    category="unresolved_edge",
                    description=f"Could not resolve edge {raw.source_name} -> {raw.target_name}",
                    source_refs=list(raw.source_refs),
                    disposition="open",
                )
            )
            continue
        if require_source_refs and not raw.source_refs:
            findings.append(
                ReviewFinding(
                    id=f"FIND-EDGE-REF-{len(findings)+1}",
                    severity="high",
                    category="missing_source_ref",
                    description=f"Rejected edge without source_refs: {raw.relation_type}",
                    disposition="open",
                )
            )
            continue
        provenance = ",".join(raw.source_refs) if raw.source_refs else "none"
        edges.append(
            KnowledgeEdge(
                id=stable_edge_id(src, raw.relation_type, tgt, provenance),
                source_id=src,
                target_id=tgt,
                relation_type=raw.relation_type,
                source_refs=list(raw.source_refs),
                derivation=raw.derivation,
                review_status="needs_review"
                if raw.derivation == "inferred_for_review"
                else "extracted",
            )
        )

    # Ground entities to sources
    for ent in [*requirements, *roles, *actions, *risks, *controls, *evidence_items]:
        for ref in ent.source_refs:
            if ref in available:
                edges.append(
                    KnowledgeEdge(
                        id=stable_edge_id(ent.id, "ENTITY_GROUNDED_IN_SOURCE", ref, ref),
                        source_id=ent.id,
                        target_id=ref,
                        relation_type="ENTITY_GROUNDED_IN_SOURCE",
                        source_refs=[ref],
                        derivation="explicit",
                        review_status="extracted",
                    )
                )

    process = Process(
        id=stable_entity_id(
            "process",
            pass_b.process_name or title,
            blocks[0].id if blocks else "NONE",
        ),
        name=pass_b.process_name or title,
        activities=[a.id for a in actions],
        flow_relations=[f for f in pass_b.flow if f],
        source_refs=[blocks[0].id] if blocks else [],
        modeling_status=pass_b.modeling_status,
    )
    workflow_processes: list[Process] = []
    if process.modeling_status != "unsupported":
        workflow_processes = _group_workflows(
            llm,
            policy_title=pass_a.title or title,
            actions=actions,
            role_names={r.id: r.name for r in roles},
            findings=findings,
        )
        workflow_processes = [p for p in workflow_processes if p.id != process.id]

    for raw in pass_e.findings:
        findings.append(
            ReviewFinding(
                id=stable_entity_id("finding", raw.description, raw.source_refs[0] if raw.source_refs else "NONE"),
                severity=raw.severity,
                category=raw.category,
                description=raw.description,
                entity_ids=[],
                source_refs=list(raw.source_refs),
                disposition="open",
            )
        )

    knowledge = PolicyKnowledge(
        policy=Policy(
            id=policy_id,
            title=pass_a.title or title,
            version=pass_a.version,
            input_path=input_path,
            source_hash=doc_hash,
            review_status="extracted",
        ),
        source_blocks=list(blocks),
        requirements=requirements,
        roles=roles,
        actions=actions,
        processes=[process, *workflow_processes],
        decisions=decisions,
        risks=risks,
        controls=controls,
        evidence=evidence_items,
        edges=edges,
        findings=findings,
        modeling_notes=list(pass_a.notes),
    )
    return reconcile_knowledge(knowledge)
