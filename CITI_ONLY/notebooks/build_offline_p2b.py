"""Build a file://-openable policies2BPMN-style offline viewer pack.

Workflows come from the pipeline run (``<run>/outputs/p2b``) when available,
otherwise from the static ``policies2BPMN/outputs`` snapshot (read-only).

Optionally embeds precomputed Pass F ``role_relevance`` + a compact entity
catalog into ``window.P2B_DATA`` for offline intelligence lenses. When those
inputs are omitted or invalid, the pack behaves exactly as before.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


ASSETS_DIRNAME = "offline_p2b_assets"
REQUIRED_ASSET_FILES = (
    "index.html",
    "app.js",
    "styles.css",
    "role_intelligence.html",
    "role_intelligence.js",
)

_CATALOG_COLLECTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("requirements", "requirement", ("text", "id")),
    ("roles", "role", ("name", "description", "id")),
    ("actions", "action", ("label", "description", "id")),
    ("decisions", "decision", ("question", "id")),
    ("risks", "risk", ("name", "description", "id")),
    ("controls", "control", ("name", "description", "id")),
    ("evidence", "evidence", ("name", "description", "id")),
    ("findings", "finding", ("description", "id")),
)


def _risk_catalog_entry(item: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    """Risk chip data: CITI code · taxonomy label when matched, else flagged as unmapped."""
    policy_wording = str(item.get("name") or artifact_id)
    code = str(item.get("risk_code") or "").strip()
    taxonomy_label = str(item.get("risk_label") or "").strip()
    origin = str(item.get("classification_origin") or "source_stated")
    if code:
        label = f"{code} · {taxonomy_label}" if taxonomy_label else code
    else:
        label = f"Unmapped: {policy_wording}"
    return {
        "type": "risk",
        "label": label,
        "policy_wording": policy_wording,
        "risk_code": code,
        "classification_origin": origin,
        "unmapped": not code,
        "source_refs": list(item.get("source_refs") or []),
    }


def risk_taxonomy_summary(canonical_catalog: dict[str, dict[str, Any]] | None) -> dict[str, int]:
    """Counts of risks by taxonomy match status, for the Overview and index."""
    risks = [e for e in (canonical_catalog or {}).values() if e.get("type") == "risk"]
    return {
        "total": len(risks),
        "mapped": sum(1 for e in risks if not e.get("unmapped") and e.get("classification_origin") != "suggested"),
        "suggested": sum(1 for e in risks if not e.get("unmapped") and e.get("classification_origin") == "suggested"),
        "unmapped": sum(1 for e in risks if e.get("unmapped")),
    }


def build_canonical_catalog(policy_knowledge: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Compact id → {type, label, source_refs} map for offline lens labels."""
    catalog: dict[str, dict[str, Any]] = {}
    for collection, artifact_type, label_keys in _CATALOG_COLLECTIONS:
        for item in policy_knowledge.get(collection) or []:
            if not isinstance(item, dict):
                continue
            artifact_id = item.get("id")
            if not artifact_id:
                continue
            if artifact_type == "risk":
                catalog[str(artifact_id)] = _risk_catalog_entry(item, str(artifact_id))
                continue
            label = ""
            for key in label_keys:
                value = item.get(key)
                if value:
                    label = str(value)
                    break
            catalog[str(artifact_id)] = {
                "type": artifact_type,
                "label": label or str(artifact_id),
                "source_refs": list(item.get("source_refs") or []),
            }
    for block in policy_knowledge.get("source_blocks") or []:
        if not isinstance(block, dict):
            continue
        block_id = block.get("id")
        if not block_id:
            continue
        excerpt = str(block.get("text") or "")[:240]
        catalog[str(block_id)] = {
            "type": "source",
            "label": excerpt or str(block_id),
            "source_refs": [str(block_id)],
            "locator": block.get("source_locator") or "",
            "section": block.get("section_path") or "",
        }
    return catalog


def load_role_intelligence(
    *,
    role_relevance_path: Path | None = None,
    policy_knowledge_path: Path | None = None,
    canonical_run_dir: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]] | None]:
    """Load optional Pass F artifact + catalog. Returns (None, None) if unavailable."""
    rr_path = Path(role_relevance_path) if role_relevance_path else None
    pk_path = Path(policy_knowledge_path) if policy_knowledge_path else None
    if canonical_run_dir is not None:
        run_dir = Path(canonical_run_dir)
        canonical = run_dir / "outputs" / "canonical"
        if not canonical.is_dir():
            # Allow passing the canonical dir itself.
            canonical = run_dir if run_dir.name == "canonical" else canonical
        if rr_path is None:
            candidate = canonical / "role_relevance.json"
            if candidate.is_file():
                rr_path = candidate
        if pk_path is None:
            candidate = canonical / "policy_knowledge.json"
            if candidate.is_file():
                pk_path = candidate

    role_relevance: dict[str, Any] | None = None
    if rr_path is not None and rr_path.is_file():
        try:
            loaded = json.loads(rr_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, dict) and isinstance(loaded.get("perspectives"), dict):
            role_relevance = loaded

    catalog: dict[str, dict[str, Any]] | None = None
    if pk_path is not None and pk_path.is_file():
        try:
            knowledge = json.loads(pk_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            knowledge = None
        if isinstance(knowledge, dict):
            catalog = build_canonical_catalog(knowledge)

    if role_relevance is None:
        return None, None
    return role_relevance, catalog or {}


# Heuristic role → workflow mapping for offline packs (LLM map may replace later).
_ROLE_WORKFLOW_HEURISTIC: dict[str, list[tuple[str, str, str]]] = {
    "business_owner": [
        ("PTP-PRECLEAR", "PRIMARY", "Get approval before you trade."),
        ("PTP-CERT", "PRIMARY", "Complete yearly training and attest."),
        ("PTP-EXCEPTION", "PRIMARY", "Ask before any exception to the policy."),
        ("PTP-DISC", "SECONDARY", "Disclose reportable accounts."),
        ("PTP-BROKER", "SECONDARY", "Keep accounts with approved brokers."),
        ("PTP-SHORT", "SECONDARY", "Avoid short-term trading profits."),
        ("PTP-PRIVATE", "SECONDARY", "Get pre-approval for private investments."),
        ("PTP-TXTYPE", "SECONDARY", "Apply the right pre-clearance rules by transaction type."),
        ("PTP-BLK", "SECONDARY", "Follow special rules when trading firm securities."),
    ],
    "compliance_officer": [
        ("PTP-VIOL", "PRIMARY", "Review and address personal trading violations."),
        ("PTP-INSIDER", "PRIMARY", "Monitor and prevent insider trading."),
        ("PTP-BLACKOUT", "PRIMARY", "Enforce blackout period restrictions."),
        ("PTP-PROHIB", "PRIMARY", "Test prohibited investment rules."),
        ("PTP-PRECLEAR", "PRIMARY", "Verify pre-clearance happened before trades."),
        ("PTP-CERT", "SECONDARY", "Confirm annual certifications completed."),
        ("PTP-MANAGED", "SECONDARY", "Review exempt managed-account handling."),
    ],
    "policy_owner": [
        ("PTP-POLICY", "PRIMARY", "Own the end-to-end personal trading policy process."),
        ("PTP-VIOL", "PRIMARY", "Ensure violation handling is covered by the policy."),
        ("PTP-EXCEPTION", "PRIMARY", "Ensure exception approval is governed."),
        ("PTP-INSIDER", "SECONDARY", "Insider trading controls must stay covered."),
        ("PTP-SEC-1", "SECONDARY", "Introduction / obligations framing for the policy."),
        ("PTP-PROHIB", "SECONDARY", "Prohibited investment rules are policy coverage."),
    ],
}


def build_role_workflow_map(
    index: list[dict[str, Any]],
    *,
    llm_map: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Build role→workflow map. Prefer validated LLM map; else heuristic filtered by index."""
    known = {str(item.get("workflow_id") or "") for item in index if item.get("workflow_id")}
    known.discard("")

    def _from_entries(entries: list[tuple[str, str, str]]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for workflow_id, relevance, why in entries:
            if workflow_id not in known:
                continue
            out.append(
                {
                    "workflow_id": workflow_id,
                    "relevance": relevance,
                    "why": why,
                }
            )
        return out

    if isinstance(llm_map, dict) and llm_map:
        result: dict[str, list[dict[str, str]]] = {}
        for role in ("business_owner", "compliance_officer", "policy_owner"):
            raw = llm_map.get(role) or []
            cleaned: list[dict[str, str]] = []
            if isinstance(raw, list):
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    wid = str(item.get("workflow_id") or "")
                    if wid not in known:
                        continue
                    cleaned.append(
                        {
                            "workflow_id": wid,
                            "relevance": str(item.get("relevance") or "SECONDARY"),
                            "why": str(item.get("why") or ""),
                        }
                    )
            result[role] = cleaned or _from_entries(_ROLE_WORKFLOW_HEURISTIC.get(role) or [])
        return result

    return {
        role: _from_entries(entries)
        for role, entries in _ROLE_WORKFLOW_HEURISTIC.items()
    }


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


def derive_role_workflow_map(
    role_relevance: dict[str, Any] | None,
    workflows: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    """Role→workflow map for run-generated workflows, from Pass F assessments.

    Differentiates the three roles by matching each role's focus tags/types and
    direct action links rather than falling back to broad source_ref overlap for
    every role.
    """
    perspectives = (role_relevance or {}).get("perspectives") or {}
    specific_wids = [w for w in workflows if w != "WF-ALL"]
    result: dict[str, list[dict[str, str]]] = {}

    for role in ("business_owner", "compliance_officer", "policy_owner"):
        assessments = (perspectives.get(role) or {}).get("assessments") or []
        focus_tags = _ROLE_FOCUS_TAGS[role]
        focus_types = _ROLE_FOCUS_TYPES[role]
        scored: list[tuple[int, int, str, str, str]] = []

        for wid, pack in workflows.items():
            # Policy Follower & Compliance Officer focus on concrete workflows when present;
            # Policy Owner keeps WF-ALL as an end-to-end coverage view.
            if wid == "WF-ALL" and specific_wids and role != "policy_owner":
                continue
            wf_json = pack.get("json") or {}
            steps = wf_json.get("steps") or []
            action_ids = {s.get("canonical_id") for s in steps if s.get("canonical_id")}
            refs = {r for s in steps for r in (s.get("source_reference_ids") or [])}

            best_rank: int | None = None
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

                # Require either a direct action hit or a role-focused source_ref hit.
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

        # Fallback if strict filtering left a role empty: relax to any direct/ref hit
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


def _match_step_guidance(
    step: dict[str, Any],
    assessments: list[dict[str, Any]],
    fallback_why: str,
) -> str:
    cid = step.get("canonical_id")
    step_refs = set(step.get("source_reference_ids") or [])
    for item in assessments:
        if not isinstance(item, dict):
            continue
        if item.get("relevance") not in _RELEVANCE_RANK:
            continue
        if cid and (
            item.get("artifact_id") == cid
            or cid in (item.get("associated_action_ids") or [])
        ):
            if item.get("why_relevant"):
                return str(item["why_relevant"])
    for item in assessments:
        if not isinstance(item, dict):
            continue
        if item.get("relevance") not in _RELEVANCE_RANK:
            continue
        if step_refs and (step_refs & set(item.get("source_refs") or [])):
            if item.get("why_relevant"):
                return str(item["why_relevant"])
    return fallback_why or str(step.get("description") or "")


def build_role_steps(
    workflows: dict[str, dict[str, Any]],
    role_workflow_map: dict[str, list[dict[str, str]]],
    *,
    role_relevance: Optional[dict[str, Any]] = None,
    policy_id: str = "",
    policy_title: str = "",
) -> dict[str, Any]:
    """Return structured JSON containing all three roles and every ordered step per role."""
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


def _run_workflows_dir(canonical_run_dir: Path | None) -> Path | None:
    """``<run>/outputs/p2b`` when the pipeline exported workflows for that run."""
    if canonical_run_dir is None:
        return None
    run_dir = Path(canonical_run_dir)
    if run_dir.name == "canonical":
        run_dir = run_dir.parent.parent
    candidate = run_dir / "outputs" / "p2b"
    return candidate if (candidate / "index.json").is_file() else None


def _vendored_bpmn_dir(repo_root: Path) -> Path | None:
    """Flat vendor dir (modeler + css + bpmn-font) shipped under assets or pack."""
    for rel in (
        ("notebooks", ASSETS_DIRNAME, "vendor"),
        ("notebooks", "offline_p2b", "vendor"),
    ):
        cand = repo_root.joinpath(*rel)
        if (cand / "bpmn-modeler.production.min.js").is_file():
            return cand
    return None


def _modeler_umd(repo_root: Path) -> Path:
    nm = (
        repo_root
        / "policies2BPMN"
        / "viewer"
        / "node_modules"
        / "bpmn-js"
        / "dist"
        / "bpmn-modeler.production.min.js"
    )
    if nm.is_file():
        return nm
    vendored = _vendored_bpmn_dir(repo_root)
    if vendored is not None:
        return vendored / "bpmn-modeler.production.min.js"
    return nm


def _bpmn_assets_dir(repo_root: Path) -> Path:
    nm = (
        repo_root
        / "policies2BPMN"
        / "viewer"
        / "node_modules"
        / "bpmn-js"
        / "dist"
        / "assets"
    )
    if nm.is_dir():
        return nm
    vendored = _vendored_bpmn_dir(repo_root)
    if vendored is not None:
        return vendored
    return nm


def _require_file(path: Path, hint: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"{hint}: missing {path}")
    return path


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        _rmtree(dest)
    shutil.copytree(src, dest)


def _rmtree(path: Path) -> None:
    """Remove a directory tree; tolerate Windows file locks where possible."""
    import sys

    def _on_rm_error(func, p, exc):  # noqa: ANN001
        import os
        import stat
        import time

        # onerror (≤3.11) passes exc_info; onexc (3.12+) passes the exception.
        cause = exc[1] if isinstance(exc, tuple) else exc
        try:
            os.chmod(p, stat.S_IWRITE)
            time.sleep(0.05)
            func(p)
        except Exception as retry_exc:  # noqa: BLE001
            raise retry_exc from cause

    # onexc is Python 3.12+; onerror remains the 3.11-compatible API.
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_on_rm_error)
    else:
        shutil.rmtree(path, onerror=_on_rm_error)


def build_offline_p2b(
    repo_root: Path,
    out_dir: Path,
    *,
    role_relevance_path: Path | None = None,
    policy_knowledge_path: Path | None = None,
    canonical_run_dir: Path | None = None,
    workflows_dir: Path | None = None,
) -> Path:
    """Package an offline HTML viewer into ``out_dir`` and return that path.

    Workflow source: ``workflows_dir`` if given, else ``<canonical_run_dir>/outputs/p2b``
    when present, else the static ``policies2BPMN/outputs`` snapshot.
    Optional role-intelligence kwargs embed Pass F output into ``P2B_DATA``.
    """
    repo_root = Path(repo_root).resolve()
    out_dir = Path(out_dir).resolve()

    run_workflows = Path(workflows_dir) if workflows_dir else _run_workflows_dir(canonical_run_dir)
    if run_workflows is not None:
        outputs = run_workflows.resolve()
        workflow_source = "pipeline_run"
        index_path = _require_file(outputs / "index.json", "run workflows index")
    else:
        outputs = repo_root / "policies2BPMN" / "outputs"
        workflow_source = "static_snapshot"
        index_path = _require_file(
            outputs / "index.json",
            "No run workflows (<run>/outputs/p2b) and no static policies2BPMN snapshot; "
            "re-run the pipeline (Cell 8) and pass canonical_run_dir",
        )
    assets_src = repo_root / "notebooks" / ASSETS_DIRNAME
    for name in REQUIRED_ASSET_FILES:
        _require_file(assets_src / name, "offline pack template")

    modeler = _modeler_umd(repo_root)
    if not modeler.is_file():
        raise FileNotFoundError(
            "bpmn-modeler UMD not found. Prefer notebooks/offline_p2b_assets/vendor/ "
            "(seeded for CITI lean packs) or run npm install under policies2BPMN/viewer. "
            f"Looked at: {modeler}"
        )
    bpmn_assets = _bpmn_assets_dir(repo_root)
    if not bpmn_assets.is_dir():
        raise FileNotFoundError(f"bpmn-js assets directory missing: {bpmn_assets}")

    index: list[dict[str, Any]] = json.loads(index_path.read_text(encoding="utf-8"))
    workflows: dict[str, dict[str, Any]] = {}
    for item in index:
        wid = item["workflow_id"]
        json_name = item.get("json") or f"{wid}.json"
        bpmn_name = item.get("bpmn") or f"{wid}.bpmn"
        json_path = _require_file(outputs / json_name, f"workflow JSON for {wid}")
        bpmn_path = _require_file(outputs / bpmn_name, f"workflow BPMN for {wid}")
        workflows[wid] = {
            "json": json.loads(json_path.read_text(encoding="utf-8")),
            "bpmn": bpmn_path.read_text(encoding="utf-8"),
        }

    policy_source_path = outputs / "policy_source.html"
    policy_source_html = (
        policy_source_path.read_text(encoding="utf-8")
        if policy_source_path.is_file()
        else "<!DOCTYPE html><html><body><p>No policy_source.html in outputs.</p></body></html>"
    )

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "index": index,
        "workflows": workflows,
        "policy_source_html": policy_source_html,
    }

    role_relevance, catalog = load_role_intelligence(
        role_relevance_path=role_relevance_path,
        policy_knowledge_path=policy_knowledge_path,
        canonical_run_dir=canonical_run_dir,
    )
    if role_relevance is not None:
        payload["role_relevance"] = role_relevance
        payload["canonical_catalog"] = catalog or {}
        payload["risk_taxonomy"] = risk_taxonomy_summary(catalog)

    llm_map = None
    if isinstance(role_relevance, dict):
        llm_map = role_relevance.get("role_workflow_map")
    if workflow_source == "pipeline_run" and not llm_map:
        payload["role_workflow_map"] = derive_role_workflow_map(role_relevance, workflows)
    else:
        payload["role_workflow_map"] = build_role_workflow_map(index, llm_map=llm_map)
    payload["role_steps"] = build_role_steps(
        workflows,
        payload["role_workflow_map"],
        role_relevance=role_relevance,
    )

    if out_dir.exists():
        try:
            _rmtree(out_dir)
        except OSError:
            # Fall back to overwrite-in-place when a browser/server holds a lock.
            pass
    out_dir.mkdir(parents=True, exist_ok=True)
    vendor = out_dir / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)

    for name in REQUIRED_ASSET_FILES:
        shutil.copy2(assets_src / name, out_dir / name)

    shutil.copy2(modeler, vendor / "bpmn-modeler.production.min.js")
    shutil.copy2(bpmn_assets / "bpmn-js.css", vendor / "bpmn-js.css")
    shutil.copy2(bpmn_assets / "diagram-js.css", vendor / "diagram-js.css")
    font_src = bpmn_assets / "bpmn-font"
    if font_src.is_dir():
        _copy_tree(font_src, vendor / "bpmn-font")

    data_js = "window.P2B_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    (out_dir / "data.js").write_text(data_js, encoding="utf-8")
    (out_dir / "role_steps.json").write_text(
        json.dumps(payload["role_steps"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "policy_source.html").write_text(policy_source_html, encoding="utf-8")

    readme = "\n".join(
        [
            "Offline policy process demo (main + role views)",
            "================================================",
            "",
            "Open index.html in a browser (file://). No network required.",
            "",
            "Main view: index.html",
            "  - Intelligence lens → All roles (main view) stays here",
            "  - Policy Follower / Compliance Officer / Policy Owner open role tabs",
            "",
            "Role views: role_intelligence.html?lens=business_owner|compliance_officer|policy_owner",
            "  - Same workflow BPMN as main, filtered per role",
            "",
            "Included: app.js, styles.css, data.js, role_intelligence.*, vendor/, policy_source.html",
            "",
        ]
    )
    (out_dir / "README_OFFLINE.txt").write_text(readme, encoding="utf-8")

    manifest = {
        "kind": "offline_p2b",
        "generated_at": payload["generated_at"],
        "workflow_count": len(index),
        "workflow_source": workflow_source,
        "source_outputs": str(outputs),
        "role_relevance_embedded": role_relevance is not None,
        "role_workflow_map_embedded": True,
        "role_steps_embedded": True,
        "role_views": [
            "role_intelligence.html?lens=business_owner",
            "role_intelligence.html?lens=compliance_officer",
            "role_intelligence.html?lens=policy_owner",
        ],
        "note": "Open index.html via file://. Role lenses open role_intelligence.html. No network required.",
    }
    (out_dir / "OFFLINE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return out_dir


_OFFLINE_ZIP_NAMES = (
    "index.html",
    "app.js",
    "styles.css",
    "data.js",
    "role_steps.json",
    "role_intelligence.html",
    "role_intelligence.js",
    "policy_source.html",
    "OFFLINE_MANIFEST.json",
    "README_OFFLINE.txt",
)


def zip_offline_pack(
    pack_dir: Path,
    zip_path: Path | None = None,
) -> Path:
    """Zip the offline pack (main + role views + vendor) for workstation demo handoff."""
    import zipfile

    pack_dir = Path(pack_dir).resolve()
    if not (pack_dir / "index.html").is_file():
        raise FileNotFoundError(f"offline pack missing index.html: {pack_dir}")

    if zip_path is None:
        zip_path = pack_dir.parent / "offline_p2b_OFFLINE_DEMO.zip"
    else:
        zip_path = Path(zip_path)
        if not zip_path.is_absolute():
            # CLI relative paths are cwd-based (e.g. notebooks/offline_p2b_OFFLINE_DEMO.zip).
            zip_path = (Path.cwd() / zip_path).resolve()
        else:
            zip_path = zip_path.resolve()
        if zip_path.is_dir():
            zip_path = zip_path / "offline_p2b_OFFLINE_DEMO.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists() and zip_path.is_file():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in _OFFLINE_ZIP_NAMES:
            src = pack_dir / name
            if src.is_file():
                zf.write(src, arcname=f"offline_p2b/{name}")
        vendor = pack_dir / "vendor"
        if vendor.is_dir():
            for path in vendor.rglob("*"):
                if path.is_file():
                    zf.write(path, arcname=f"offline_p2b/{path.relative_to(pack_dir).as_posix()}")
    return zip_path


def _latest_canonical_run_dir(repo_root: Path) -> Path | None:
    """Newest notebooks/policy_runs/*/…/outputs/canonical with role_relevance.json."""
    runs_root = Path(repo_root) / "notebooks" / "policy_runs"
    if not runs_root.is_dir():
        return None
    candidates: list[Path] = []
    for canonical in runs_root.glob("*/*/outputs/canonical"):
        if (canonical / "role_relevance.json").is_file():
            candidates.append(canonical)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


if __name__ == "__main__":
    import argparse

    root = Path(__file__).resolve().parents[1]
    target = root / "notebooks" / "offline_p2b"
    parser = argparse.ArgumentParser(description="Build and/or zip offline_p2b demo pack")
    parser.add_argument(
        "--zip-only",
        action="store_true",
        help="Only zip an existing notebooks/offline_p2b pack (no rebuild)",
    )
    parser.add_argument(
        "--zip-path",
        type=Path,
        default=None,
        help="Output zip path (default: notebooks/offline_p2b_OFFLINE_DEMO.zip)",
    )
    args = parser.parse_args()

    if not args.zip_only:
        canonical = _latest_canonical_run_dir(root)
        build_kwargs: dict[str, Path] = {}
        if canonical is not None:
            build_kwargs["canonical_run_dir"] = canonical
            build_kwargs["role_relevance_path"] = canonical / "role_relevance.json"
            pk = canonical / "policy_knowledge.json"
            if pk.is_file():
                build_kwargs["policy_knowledge_path"] = pk
            print("embedding_role_relevance", canonical)
        built = build_offline_p2b(root, target, **build_kwargs)
        print(built / "index.html")
        print((built / "index.html").as_uri())
    else:
        built = target

    zipped = zip_offline_pack(built, args.zip_path)
    print("offline_demo_zip", zipped)
