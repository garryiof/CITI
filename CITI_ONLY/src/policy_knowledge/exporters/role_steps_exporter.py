"""Structured per-role ordered steps JSON export (role_steps.json)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_RELEVANCE_RANK = {"PRIMARY": 0, "SECONDARY": 1}

_ROLE_FOCUS_TAGS: dict[str, set[str]] = {
    "business_owner": {
        "applicable_requirement",
        "required_action",
        "prohibited_action",
        "deadline_or_approval",
        "evidence_to_retain",
        "exception_handling",
    },
    "compliance_officer": {
        "compliance_obligation",
        "testable_requirement",
        "control_verification",
        "evidence_validation",
        "exception_or_breach",
        "test_scenario",
        "operational_risk",
    },
    "policy_owner": {
        "policy_objective",
        "risk_coverage",
        "governance_requirement",
        "control_requirement",
        "ownership_accountability",
        "regulatory_dependency",
        "ambiguity_or_gap",
        "change_impact",
    },
}

_ROLE_FOCUS_TYPES: dict[str, set[str]] = {
    "business_owner": {"action", "requirement", "decision"},
    "compliance_officer": {"risk", "control", "evidence", "finding"},
    "policy_owner": {"finding", "role", "requirement", "risk"},
}

_ROLE_META: dict[str, tuple[str, str, str]] = {
    "business_owner": (
        "Policy Follower",
        "Operational obligations and sequential steps you must follow.",
        "What you must do",
    ),
    "compliance_officer": (
        "Compliance Officer",
        "Controls, monitoring, and compliance verification steps across the policy.",
        "What you monitor and test",
    ),
    "policy_owner": (
        "Policy Owner",
        "Policy ownership, governance checkpoints, and coverage across the policy.",
        "Governance and coverage focus",
    ),
}


def derive_role_workflow_map(
    role_relevance: Optional[dict[str, Any]],
    workflows: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    perspectives = (role_relevance or {}).get("perspectives") or {}
    specific_wids = [w for w in workflows if w != "WF-ALL"]
    result: dict[str, list[dict[str, str]]] = {}

    for role in ("business_owner", "compliance_officer", "policy_owner"):
        assessments = (perspectives.get(role) or {}).get("assessments") or []
        focus_tags = _ROLE_FOCUS_TAGS[role]
        focus_types = _ROLE_FOCUS_TYPES[role]
        scored: list[tuple[int, int, str, str, str]] = []

        for wid, pack in workflows.items():
            if wid == "WF-ALL" and specific_wids and role != "policy_owner":
                continue
            wf_json = pack.get("json") or {}
            steps = wf_json.get("steps") or []
            action_ids = {s.get("canonical_id") for s in steps if s.get("canonical_id")}
            refs = {r for s in steps for r in (s.get("source_reference_ids") or [])}

            best_rank: Optional[int] = None
            best_why = ""
            score = 0
            for item in assessments:
                if not isinstance(item, dict):
                    continue
                relevance = str(item.get("relevance") or "")
                if relevance not in _RELEVANCE_RANK:
                    continue
                tags = set(item.get("lens_tags") or [])
                atype = str(item.get("artifact_type") or "")
                in_role_focus = bool(tags & focus_tags) or (not tags and atype in focus_types)

                direct_hit = bool(
                    item.get("artifact_id") in action_ids
                    or (action_ids & set(item.get("associated_action_ids") or []))
                )
                ref_hit = bool(refs & set(item.get("source_refs") or []))

                if not direct_hit and not (ref_hit and in_role_focus):
                    continue
                if role == "compliance_officer" and not (
                    in_role_focus
                    or item.get("associated_risk_ids")
                    or item.get("associated_control_ids")
                    or item.get("associated_evidence_ids")
                ):
                    continue
                if role == "policy_owner" and not in_role_focus and wid != "WF-ALL":
                    continue

                rank = _RELEVANCE_RANK[relevance]
                weight = (3 if direct_hit else 1) + (2 if in_role_focus else 0) + (2 if rank == 0 else 1)
                score += weight
                if best_rank is None or rank < best_rank:
                    best_rank = rank
                    best_why = str(item.get("why_relevant") or "")

            if best_rank is not None:
                rel_label = "PRIMARY" if best_rank == 0 else "SECONDARY"
                scored.append((best_rank, -score, wid, rel_label, best_why))

        if not scored:
            for wid, pack in workflows.items():
                if wid == "WF-ALL" and specific_wids and role != "policy_owner":
                    continue
                steps = (pack.get("json") or {}).get("steps") or []
                action_ids = {s.get("canonical_id") for s in steps if s.get("canonical_id")}
                refs = {r for s in steps for r in (s.get("source_reference_ids") or [])}
                for item in assessments:
                    if not isinstance(item, dict):
                        continue
                    relevance = str(item.get("relevance") or "")
                    if relevance not in _RELEVANCE_RANK:
                        continue
                    if (
                        item.get("artifact_id") in action_ids
                        or (action_ids & set(item.get("associated_action_ids") or []))
                        or (refs & set(item.get("source_refs") or []))
                    ):
                        scored.append(
                            (_RELEVANCE_RANK[relevance], -1, wid, relevance, str(item.get("why_relevant") or ""))
                        )
                        break

        scored.sort()
        entries = [{"workflow_id": wid, "relevance": rel, "why": why} for _, _, wid, rel, why in scored]
        if not entries and "WF-ALL" in workflows:
            entries.append(
                {"workflow_id": "WF-ALL", "relevance": "SECONDARY", "why": "Whole-policy view."}
            )
        result[role] = entries
    return result


def _match_step_guidance(
    step: dict[str, Any],
    assessments: list[dict[str, Any]],
    fallback_why: str,
) -> str:
    cid = step.get("canonical_id")
    step_refs = set(step.get("source_reference_ids") or [])
    for item in assessments:
        if not isinstance(item, dict) or item.get("relevance") not in _RELEVANCE_RANK:
            continue
        if cid and (
            item.get("artifact_id") == cid
            or cid in (item.get("associated_action_ids") or [])
        ):
            if item.get("why_relevant"):
                return str(item["why_relevant"])
    for item in assessments:
        if not isinstance(item, dict) or item.get("relevance") not in _RELEVANCE_RANK:
            continue
        if step_refs and (step_refs & set(item.get("source_refs") or [])):
            if item.get("why_relevant"):
                return str(item["why_relevant"])
    return fallback_why or str(step.get("description") or "")


def build_role_steps_payload(
    workflows: dict[str, dict[str, Any]],
    role_workflow_map: dict[str, list[dict[str, str]]],
    *,
    role_relevance: Optional[dict[str, Any]] = None,
    policy_id: str = "",
    policy_title: str = "",
) -> dict[str, Any]:
    perspectives = (role_relevance or {}).get("perspectives") or {}
    inferred_policy_id = policy_id or str((role_relevance or {}).get("policy_id") or "")
    inferred_title = policy_title
    if not inferred_title or not inferred_policy_id:
        for pack in workflows.values():
            pol = ((pack.get("json") or {}).get("policy")) or {}
            if not inferred_policy_id and pol.get("policy_id"):
                inferred_policy_id = str(pol["policy_id"])
            if not inferred_title and pol.get("policy_title"):
                inferred_title = str(pol["policy_title"])
            if inferred_policy_id and inferred_title:
                break

    roles_out: dict[str, dict[str, Any]] = {}
    for role_key in ("business_owner", "compliance_officer", "policy_owner"):
        role_label, purpose, step_focus = _ROLE_META[role_key]
        assessments = (perspectives.get(role_key) or {}).get("assessments") or []
        entries = role_workflow_map.get(role_key) or []

        wf_summaries: list[dict[str, Any]] = []
        role_steps: list[dict[str, Any]] = []
        order_num = 0

        for entry in entries:
            wid = str(entry.get("workflow_id") or "")
            wf_json = (workflows.get(wid) or {}).get("json") or {}
            if not wf_json:
                continue
            wf_title = str(wf_json.get("workflow_title") or wid)
            relevance = str(entry.get("relevance") or "SECONDARY")
            why = str(entry.get("why") or wf_json.get("workflow_summary") or "")
            actor_map = {
                str(a.get("actor_id")): str(a.get("name") or a.get("actor_id"))
                for a in (wf_json.get("actors") or [])
                if isinstance(a, dict) and a.get("actor_id")
            }
            gw_by_after = {
                str(g.get("after_step_id")): g
                for g in (wf_json.get("gateways") or [])
                if isinstance(g, dict) and g.get("after_step_id")
            }

            steps = wf_json.get("steps") or []
            wf_summaries.append(
                {
                    "workflow_id": wid,
                    "workflow_title": wf_title,
                    "relevance": relevance,
                    "why": why,
                    "step_count": len(steps),
                }
            )
            for idx, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    continue
                order_num += 1
                step_id = str(step.get("step_id") or f"STEP-{idx:03d}")
                title = str(step.get("title") or step.get("label") or step.get("name") or step_id)
                actor_id = str(step.get("actor_id") or "")
                actor = actor_map.get(
                    actor_id,
                    str(step.get("actor_role") or actor_id or "Unassigned"),
                )
                gw = gw_by_after.get(step_id)
                gateway_after = None
                if gw:
                    gateway_after = {
                        "gateway_id": gw.get("gateway_id"),
                        "question": gw.get("question"),
                        "explicit_or_inferred": gw.get("explicit_or_inferred"),
                        "branches": [
                            {
                                "label": br.get("label") or br.get("condition"),
                                "outcome": br.get("outcome"),
                            }
                            for br in (gw.get("branches") or [])
                            if isinstance(br, dict)
                        ],
                    }
                role_steps.append(
                    {
                        "order": order_num,
                        "workflow_id": wid,
                        "workflow_title": wf_title,
                        "relevance": relevance,
                        "step_id": step_id,
                        "step_code": f"{wid}:{step_id}",
                        "sequence": int(step.get("sequence") or idx),
                        "title": title,
                        "description": str(step.get("description") or ""),
                        "actor": actor,
                        "action_type": str(step.get("action_type") or "MANDATORY_ACTION"),
                        "explicit_or_inferred": str(step.get("explicit_or_inferred") or "EXPLICIT"),
                        "path_outcome": step.get("path_outcome"),
                        "role_focus": step_focus,
                        "role_guidance": _match_step_guidance(step, assessments, why),
                        "gateway_after": gateway_after,
                        "source_reference_ids": list(step.get("source_reference_ids") or []),
                    }
                )

        roles_out[role_key] = {
            "role_key": role_key,
            "role_label": role_label,
            "purpose": purpose,
            "workflow_count": len(wf_summaries),
            "total_steps": len(role_steps),
            "workflows": wf_summaries,
            "steps": role_steps,
        }

    return {
        "schema_version": "role_steps-1.0",
        "policy_id": inferred_policy_id,
        "policy_title": inferred_title,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roles": roles_out,
    }


def export_role_steps(
    p2b_dir: Path,
    role_relevance: Optional[dict[str, Any]],
    output_path: Path,
    *,
    policy_id: str = "",
    policy_title: str = "",
) -> Path:
    """Build and write structured role_steps.json from exported p2b workflows + Pass F."""
    p2b_dir = Path(p2b_dir)
    index_path = p2b_dir / "index.json"
    workflows: dict[str, dict[str, Any]] = {}
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for item in index:
            wid = item.get("workflow_id")
            if not wid:
                continue
            wf_path = p2b_dir / (item.get("json") or f"{wid}.json")
            if wf_path.is_file():
                workflows[wid] = {"json": json.loads(wf_path.read_text(encoding="utf-8"))}

    role_map = derive_role_workflow_map(role_relevance, workflows)
    payload = build_role_steps_payload(
        workflows,
        role_map,
        role_relevance=role_relevance,
        policy_id=policy_id,
        policy_title=policy_title,
    )
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
