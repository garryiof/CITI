"""policies2BPMN-format workflows (index.json + per-workflow JSON/BPMN) from a pipeline run.

Feeds the offline_p2b viewer pack so it shows the policy that was actually processed,
instead of the static policies2BPMN snapshot.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Optional

from lxml import etree

from policy_knowledge.model.schemas import Action, Decision, PolicyKnowledge, Process, SourceBlock

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
BIOC_NS = "http://bpmn.io/schema/bpmn/biocolor/1.0"
NSMAP = {None: BPMN_NS, "bpmndi": BPMNDI_NS, "dc": DC_NS, "di": DI_NS, "bioc": BIOC_NS}

UNASSIGNED_ACTOR = "ACT-UNASSIGNED"
ALL_WORKFLOW_ID = "WF-ALL"

_TASK_W, _TASK_H = 130.0, 80.0
_GW = 50.0
_EVENT = 36.0
_COL = 190.0
_ROW = 195.0
_X0, _Y0 = 110.0, 60.0
_REJECT_DY = 115.0

_GREEN_STROKE, _GREEN_FILL = "#2F7D4F", "#E4F2E9"
_RED_STROKE, _RED_FILL = "#B3402E", "#F8E3DD"

_PROHIBITION_RE = re.compile(
    r"\b(must not|may not|prohibited|forbidden|not permitted|shall not|do not)\b",
    re.IGNORECASE,
)
_APPROVAL_RE = re.compile(
    r"\b(pre-?clear\w*|approv\w*|permission|authoriz\w*|consent|clearance|exception request)\b",
    re.IGNORECASE,
)
_NEGATIVE_BRANCH_RE = re.compile(
    r"\b(reject\w*|denied|deny|prohibit\w*|not approved|not permitted|fail\w*|no|violat\w*|stop)\b",
    re.IGNORECASE,
)
_POSITIVE_BRANCH_RE = re.compile(
    r"\b(approv\w*|permit\w*|allow\w*|grant\w*|yes|pass\w*|proceed|clear\w*)\b",
    re.IGNORECASE,
)


def _ordered_actions(process: Process, actions_by_id: dict[str, Action]) -> list[Action]:
    return [actions_by_id[a] for a in process.activities if a in actions_by_id]


def _actor_for(action: Action, role_names: dict[str, str]) -> tuple[str, str]:
    for role_id in action.actor_role_ids:
        if role_id in role_names:
            return role_id, role_names[role_id]
    return UNASSIGNED_ACTOR, "Unassigned"


def _is_prohibited_action(action: Action) -> bool:
    return bool(_PROHIBITION_RE.search(f"{action.label} {action.description}"))


def _is_approval_action(action: Action) -> bool:
    return bool(_APPROVAL_RE.search(f"{action.label} {action.description}"))


def _branch_label(branch: dict) -> str:
    for key in ("condition", "label", "name", "outcome"):
        val = branch.get(key)
        if val:
            return str(val).strip()
    return ""


def _branch_target_label(branch: dict) -> str:
    for key in ("next_action_label", "target", "action", "next_step"):
        val = branch.get(key)
        if val:
            return str(val).strip()
    return ""


def _branch_is_negative(branch: dict) -> bool:
    outcome = str(branch.get("outcome") or "").upper()
    if outcome in ("PROHIBITED", "REJECTED", "STOP", "DENIED"):
        return True
    if outcome in ("PROCEED", "APPROVED", "PERMITTED"):
        return False
    label = _branch_label(branch)
    if _NEGATIVE_BRANCH_RE.search(label) and not _POSITIVE_BRANCH_RE.search(label):
        return True
    return False


def _match_decisions(
    workflow_id: str,
    members: list[Action],
    decisions: list[Decision],
    blocks_by_id: dict[str, SourceBlock],
) -> list[tuple[int, dict]]:
    """Return list of (insert_after_step_idx, gateway_spec) for this workflow."""
    if not members:
        return []
    label_to_idx = {a.label.strip().lower(): i for i, a in enumerate(members)}
    workflow_refs = {r for a in members for r in a.source_refs if r in blocks_by_id}

    matched: list[tuple[int, dict]] = []
    used_positions: set[int] = set()

    for dec in decisions:
        dec_refs = [r for r in dec.source_refs if r in blocks_by_id]
        target_idx: Optional[int] = None
        pos_label = "Approved"
        neg_label = "Rejected / Prohibited"
        neg_end_label = "Must not proceed — prohibited or rejected"
        has_explicit_branch = False

        for br in dec.branches or []:
            if not isinstance(br, dict):
                continue
            has_explicit_branch = True
            lbl = _branch_label(br)
            tgt = _branch_target_label(br).lower()
            if _branch_is_negative(br):
                if lbl:
                    neg_label = lbl
                if br.get("end_label"):
                    neg_end_label = str(br["end_label"]).strip()
            else:
                if lbl:
                    pos_label = lbl
                if tgt and tgt in label_to_idx:
                    target_idx = label_to_idx[tgt]

        # Decide whether this decision belongs to this workflow.
        belongs = False
        if target_idx is not None:
            belongs = True
        elif workflow_id == ALL_WORKFLOW_ID:
            belongs = True
        elif dec_refs and (set(dec_refs) & workflow_refs):
            belongs = True
        if not belongs:
            continue

        # Determine which step index the gateway sits immediately after.
        if target_idx is not None and target_idx > 0:
            after_idx = target_idx - 1
        else:
            ref_hits = [i for i, a in enumerate(members) if set(a.source_refs) & set(dec_refs)]
            approval_hits = [i for i, a in enumerate(members) if _is_approval_action(a)]
            if ref_hits:
                after_idx = ref_hits[0]
            elif approval_hits:
                after_idx = approval_hits[0]
            else:
                after_idx = 0
        if after_idx in used_positions:
            continue
        used_positions.add(after_idx)
        matched.append(
            (
                after_idx,
                {
                    "question": dec.question,
                    "source_reference_ids": dec_refs,
                    "explicit_or_inferred": "EXPLICIT",
                    "pos_label": pos_label,
                    "neg_label": neg_label,
                    "neg_end_label": neg_end_label,
                    "has_branches": has_explicit_branch,
                },
            )
        )

    # Fallback: if the workflow contains an approval/pre-clearance step but Pass B
    # emitted no decision for it, add a clearly marked INFERRED approval gateway so
    # reviewers can see the Approved vs Rejected/Prohibited split.
    if not matched:
        for idx, action in enumerate(members):
            if _is_approval_action(action):
                refs = [r for r in action.source_refs if r in blocks_by_id]
                matched.append(
                    (
                        idx,
                        {
                            "question": "Is the request approved and transaction permitted?",
                            "source_reference_ids": refs,
                            "explicit_or_inferred": "INFERRED",
                            "pos_label": "Approved",
                            "neg_label": "Rejected / Prohibited",
                            "neg_end_label": "Must not proceed — prohibited or rejected",
                            "has_branches": True,
                        },
                    )
                )
                break

    matched.sort(key=lambda pair: pair[0])
    return matched


def _workflow_json(
    workflow_id: str,
    title: str,
    summary: Optional[str],
    trigger: Optional[str],
    members: list[Action],
    knowledge: PolicyKnowledge,
    blocks_by_id: dict[str, SourceBlock],
) -> dict:
    role_names = {r.id: r.name for r in knowledge.roles}
    actors: list[dict] = []
    seen_actors: set[str] = set()
    steps: list[dict] = []
    ref_ids: list[str] = []

    matched_gateways = _match_decisions(workflow_id, members, knowledge.decisions, blocks_by_id)
    gw_by_after_idx: dict[int, tuple[str, str, dict]] = {}
    for gw_num, (after_idx, spec) in enumerate(matched_gateways, start=1):
        gw_by_after_idx[after_idx] = (f"GATEWAY-{gw_num:03d}", f"END-REJ-{gw_num:03d}", spec)

    first_gw_idx = matched_gateways[0][0] if matched_gateways else None

    for idx, action in enumerate(members):
        actor_id, actor_name = _actor_for(action, role_names)
        if actor_id not in seen_actors:
            seen_actors.add(actor_id)
            actors.append(
                {
                    "actor_id": actor_id,
                    "name": actor_name,
                    "actor_type": "BUSINESS_FUNCTION",
                    "bpmn_lane": actor_name,
                }
            )
        refs = [r for r in action.source_refs if r in blocks_by_id]
        ref_ids.extend(r for r in refs if r not in ref_ids)
        prohibited = _is_prohibited_action(action)
        after_approval = first_gw_idx is not None and idx > first_gw_idx and not prohibited
        if idx in gw_by_after_idx:
            next_id = gw_by_after_idx[idx][0]
        elif idx + 1 < len(members):
            next_id = f"STEP-{idx + 2:03d}"
        else:
            next_id = "END-001"
        steps.append(
            {
                "step_id": f"STEP-{idx + 1:03d}",
                "sequence": idx + 1,
                "title": action.label,
                "description": action.description,
                "actor_id": actor_id,
                "action_type": "PROHIBITED_ACTION" if prohibited else "MANDATORY_ACTION",
                "bpmn_type": "userTask",
                "source_reference_ids": refs,
                "explicit_or_inferred": "EXPLICIT",
                "canonical_id": action.id,
                "next_step_ids": [next_id],
                "preconditions": list(action.preconditions or []),
                "outputs": list(action.outputs or []),
                "deadline_id": None,
                "exception_ids": [],
                "path_outcome": (
                    "PROHIBITED" if prohibited else ("APPROVED" if after_approval else None)
                ),
                "color": "red" if prohibited else ("green" if after_approval else None),
            }
        )

    gateways: list[dict] = []
    rejected_ends: list[dict] = []
    for after_idx, (gw_id, end_rej_id, spec) in sorted(gw_by_after_idx.items()):
        for ref in spec["source_reference_ids"]:
            if ref not in ref_ids:
                ref_ids.append(ref)
        pos_target = f"STEP-{after_idx + 2:03d}" if after_idx + 1 < len(members) else "END-001"
        gateways.append(
            {
                "gateway_id": gw_id,
                "gateway_code": gw_id,
                "gateway_type": "exclusiveGateway",
                "question": spec["question"],
                "after_step_id": f"STEP-{after_idx + 1:03d}",
                "actor_id": steps[after_idx]["actor_id"],
                "source_reference_ids": list(spec["source_reference_ids"]),
                "explicit_or_inferred": spec["explicit_or_inferred"],
                "branches": [
                    {
                        "label": spec["pos_label"],
                        "condition": spec["pos_label"],
                        "outcome": "APPROVED",
                        "target_id": pos_target,
                        "color": "green",
                    },
                    {
                        "label": spec["neg_label"],
                        "condition": spec["neg_label"],
                        "outcome": "PROHIBITED",
                        "target_id": end_rej_id,
                        "color": "red",
                    },
                ],
            }
        )
        rejected_ends.append(
            {
                "event_id": end_rej_id,
                "event_type": "endEvent",
                "title": spec["neg_end_label"],
                "actor_id": steps[after_idx]["actor_id"],
                "after_gateway_id": gw_id,
                "path_outcome": "PROHIBITED",
                "color": "red",
            }
        )

    source_references = []
    for ref in ref_ids:
        block = blocks_by_id[ref]
        source_references.append(
            {
                "reference_id": ref,
                "section_id": block.section_path,
                "section_title": block.section_path,
                "page": None,
                "paragraph": block.sequence,
                "anchor": ref,
                "source_html": "policy_source.html",
                "quoted_text": block.text[:600],
            }
        )

    start = {
        "event_id": "START-001",
        "event_type": "startEvent",
        "title": trigger or "Start",
        "next_step_id": steps[0]["step_id"] if steps else "END-001",
        "source_reference_ids": ref_ids[:1],
        "path_outcome": None,
        "color": None,
    }
    end = {
        "event_id": "END-001",
        "event_type": "endEvent",
        "title": "Process completed",
        "path_outcome": "APPROVED" if gateways else None,
        "color": "green" if gateways else None,
    }
    end_events = [end, *rejected_ends]
    return {
        "workflow_id": workflow_id,
        "workflow_title": title,
        "workflow_summary": summary or "",
        "policy": {
            "policy_id": knowledge.policy.id,
            "policy_title": knowledge.policy.title,
            "policy_version": knowledge.policy.version,
            "source_file": Path(knowledge.policy.input_path).name if knowledge.policy.input_path else "",
        },
        "source_references": source_references,
        "trigger": {"type": "USER_INTENT", "description": trigger or ""},
        "actors": actors,
        "steps": steps,
        "gateways": gateways,
        "events": [start, *end_events],
        "start_event": start,
        "end_events": end_events,
        "conditions": [],
        "exceptions": [],
        "deadlines": [],
        "records": [],
        "controls": [],
        "ambiguities": [],
        "overall_confidence": None,
        "review_status": "PENDING",
    }


def _sub(parent: etree._Element, tag: str, **attrs: str) -> etree._Element:
    el = etree.SubElement(parent, tag)
    for key, value in attrs.items():
        el.set(key, value)
    return el


def _set_color(el: etree._Element, color: Optional[str], *, fill: bool = True) -> None:
    if color == "green":
        el.set(f"{{{BIOC_NS}}}stroke", _GREEN_STROKE)
        if fill:
            el.set(f"{{{BIOC_NS}}}fill", _GREEN_FILL)
    elif color == "red":
        el.set(f"{{{BIOC_NS}}}stroke", _RED_STROKE)
        if fill:
            el.set(f"{{{BIOC_NS}}}fill", _RED_FILL)


def _workflow_bpmn(workflow: dict) -> bytes:
    wid = workflow["workflow_id"]
    steps = workflow["steps"]
    gateways = workflow.get("gateways") or []
    end_events = workflow.get("end_events") or [{"event_id": "END-001", "title": "Process completed"}]
    rejected_ends = [e for e in end_events if e["event_id"] != "END-001"]
    actors = workflow["actors"] or [{"actor_id": UNASSIGNED_ACTOR, "name": "Unassigned"}]
    row_of = {a["actor_id"]: i for i, a in enumerate(actors)}
    gw_after = {g["after_step_id"]: g for g in gateways}

    defs = etree.Element(f"{{{BPMN_NS}}}definitions", nsmap=NSMAP)
    defs.set("id", f"Defs_{wid}")
    defs.set("targetNamespace", "http://policies2bpmn.local/workflows")
    collab = _sub(defs, f"{{{BPMN_NS}}}collaboration", id=f"Collab_{wid}")
    _sub(
        collab,
        f"{{{BPMN_NS}}}participant",
        id=f"Participant_{wid}",
        name=workflow["policy"]["policy_title"],
        processRef=f"Process_{wid}",
    )
    proc = _sub(
        defs,
        f"{{{BPMN_NS}}}process",
        id=f"Process_{wid}",
        name=workflow["workflow_title"],
        isExecutable="false",
    )

    first_actor = steps[0]["actor_id"] if steps else actors[0]["actor_id"]
    last_actor = steps[-1]["actor_id"] if steps else first_actor
    lane_nodes: dict[str, list[str]] = {a["actor_id"]: [] for a in actors}
    lane_nodes.setdefault(first_actor, []).append("START-001")
    for step in steps:
        lane_nodes.setdefault(step["actor_id"], []).append(step["step_id"])
        if step["step_id"] in gw_after:
            gw = gw_after[step["step_id"]]
            lane_nodes.setdefault(gw["actor_id"], []).append(gw["gateway_id"])
    lane_nodes.setdefault(last_actor, []).append("END-001")
    for rej in rejected_ends:
        lane_nodes.setdefault(rej.get("actor_id") or last_actor, []).append(rej["event_id"])

    lane_set = _sub(proc, f"{{{BPMN_NS}}}laneSet", id=f"LaneSet_{wid}")
    for actor in actors:
        lane = _sub(lane_set, f"{{{BPMN_NS}}}lane", id=f"Lane_{actor['actor_id']}", name=actor["name"])
        for node_id in lane_nodes.get(actor["actor_id"], []):
            _sub(lane, f"{{{BPMN_NS}}}flowNodeRef").text = node_id

    _sub(proc, f"{{{BPMN_NS}}}startEvent", id="START-001", name=workflow["start_event"]["title"])
    for step in steps:
        _sub(proc, f"{{{BPMN_NS}}}userTask", id=step["step_id"], name=step["title"])
    for gw in gateways:
        _sub(proc, f"{{{BPMN_NS}}}exclusiveGateway", id=gw["gateway_id"], name=gw["question"])
    for end_ev in end_events:
        _sub(proc, f"{{{BPMN_NS}}}endEvent", id=end_ev["event_id"], name=end_ev["title"])

    # Main linear spine: START -> steps (with inline gateways) -> END-001
    spine: list[str] = ["START-001"]
    for step in steps:
        spine.append(step["step_id"])
        if step["step_id"] in gw_after:
            spine.append(gw_after[step["step_id"]]["gateway_id"])
    spine.append("END-001")

    step_by_id = {s["step_id"]: s for s in steps}
    gw_by_id = {g["gateway_id"]: g for g in gateways}
    end_by_id = {e["event_id"]: e for e in end_events}

    flows: list[tuple[str, str, str, Optional[str], Optional[str]]] = []
    flow_seq = 0
    for i in range(len(spine) - 1):
        src, tgt = spine[i], spine[i + 1]
        flow_seq += 1
        flow_id = f"Flow_{flow_seq:03d}"
        flow_name: Optional[str] = None
        flow_color: Optional[str] = None
        if src in gw_by_id:
            pos_branch = next((b for b in gw_by_id[src]["branches"] if b.get("outcome") != "PROHIBITED"), None)
            if pos_branch:
                flow_name = pos_branch.get("label")
                flow_color = pos_branch.get("color") or "green"
        elif tgt in step_by_id and step_by_id[tgt].get("color"):
            flow_color = step_by_id[tgt]["color"]
        elif tgt == "END-001" and end_by_id["END-001"].get("color"):
            flow_color = end_by_id["END-001"]["color"]
        attrs = {"id": flow_id, "sourceRef": src, "targetRef": tgt}
        if flow_name:
            attrs["name"] = flow_name
        _sub(proc, f"{{{BPMN_NS}}}sequenceFlow", **attrs)
        flows.append((flow_id, src, tgt, flow_name, flow_color))

    # Rejected / prohibited branches from gateways to rejected end events
    for gw in gateways:
        for br in gw["branches"]:
            if br.get("outcome") == "PROHIBITED":
                flow_seq += 1
                flow_id = f"Flow_{flow_seq:03d}"
                attrs = {
                    "id": flow_id,
                    "sourceRef": gw["gateway_id"],
                    "targetRef": br["target_id"],
                }
                if br.get("label"):
                    attrs["name"] = br["label"]
                _sub(proc, f"{{{BPMN_NS}}}sequenceFlow", **attrs)
                flows.append((flow_id, gw["gateway_id"], br["target_id"], br.get("label"), "red"))

    actor_of = {"START-001": first_actor, "END-001": last_actor}
    actor_of.update({s["step_id"]: s["actor_id"] for s in steps})
    actor_of.update({g["gateway_id"]: g["actor_id"] for g in gateways})
    node_color: dict[str, Optional[str]] = {s["step_id"]: s.get("color") for s in steps}
    for e in end_events:
        node_color[e["event_id"]] = e.get("color")

    bounds: dict[str, tuple[float, float, float, float]] = {}
    for col, node_id in enumerate(spine):
        if node_id in ("START-001", "END-001"):
            w, h = _EVENT, _EVENT
        elif node_id in gw_by_id:
            w, h = _GW, _GW
        else:
            w, h = _TASK_W, _TASK_H
        cx = _X0 + col * _COL
        cy = _Y0 + row_of.get(actor_of[node_id], 0) * _ROW + _TASK_H / 2
        bounds[node_id] = (cx - w / 2, cy - h / 2, w, h)

    for rej in rejected_ends:
        gw_id = rej["after_gateway_id"]
        gx, gy, gw_w, gw_h = bounds[gw_id]
        cx = gx + gw_w / 2 + _COL * 0.75
        cy = gy + gw_h / 2 + _REJECT_DY
        bounds[rej["event_id"]] = (cx - _EVENT / 2, cy - _EVENT / 2, _EVENT, _EVENT)

    diagram = _sub(defs, f"{{{BPMNDI_NS}}}BPMNDiagram", id=f"Diagram_{wid}")
    plane = _sub(diagram, f"{{{BPMNDI_NS}}}BPMNPlane", id=f"Plane_{wid}", bpmnElement=f"Process_{wid}")
    for node_id in [*spine, *[r["event_id"] for r in rejected_ends]]:
        x, y, w, h = bounds[node_id]
        shape = _sub(plane, f"{{{BPMNDI_NS}}}BPMNShape", id=f"Shape_{node_id}", bpmnElement=node_id)
        _set_color(shape, node_color.get(node_id), fill=True)
        _sub(shape, f"{{{DC_NS}}}Bounds", x=str(x), y=str(y), width=str(w), height=str(h))

    for flow_id, src, tgt, _name, fcolor in flows:
        sx, sy, sw, sh = bounds[src]
        tx, ty, tw, th = bounds[tgt]
        x1, y1 = sx + sw, sy + sh / 2
        x2, y2 = tx, ty + th / 2
        points = [(x1, y1), (x2, y2)]
        if abs(y1 - y2) > 0.5:
            mid = (x1 + x2) / 2
            points = [(x1, y1), (mid, y1), (mid, y2), (x2, y2)]
        edge = _sub(plane, f"{{{BPMNDI_NS}}}BPMNEdge", id=f"Edge_{flow_id}", bpmnElement=flow_id)
        _set_color(edge, fcolor, fill=False)
        for px, py in points:
            _sub(edge, f"{{{DI_NS}}}waypoint", x=str(px), y=str(py))

    return etree.tostring(defs, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def _policy_source_html(knowledge: PolicyKnowledge) -> str:
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{html.escape(knowledge.policy.title)}</title>",
        "<style>body{font-family:Segoe UI,Arial,sans-serif;max-width:900px;margin:2rem auto;"
        "line-height:1.5;color:#1f2937}h2{font-size:1rem;color:#475569;margin-top:2rem}"
        "p{white-space:pre-wrap}p:target{background:#fef9c3}</style>",
        "</head><body>",
        f"<h1>{html.escape(knowledge.policy.title)}</h1>",
    ]
    current_section = None
    for block in sorted(knowledge.source_blocks, key=lambda b: b.sequence):
        if block.section_path != current_section:
            current_section = block.section_path
            parts.append(f"<h2>{html.escape(current_section)}</h2>")
        parts.append(f'<p id="{html.escape(block.id)}">{html.escape(block.text)}</p>')
    parts.append("</body></html>")
    return "\n".join(parts)


def export_p2b_workflows(knowledge: PolicyKnowledge, output_dir: Path) -> Path:
    """Write index.json, <WF>.json, <WF>.bpmn and policy_source.html; return output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    actions_by_id = {a.id: a for a in knowledge.actions}
    blocks_by_id = {b.id: b for b in knowledge.source_blocks}

    candidates: list[tuple[str, Process]] = []
    if knowledge.processes:
        whole = knowledge.processes[0]
        if whole.modeling_status != "unsupported" and _ordered_actions(whole, actions_by_id):
            candidates.append((ALL_WORKFLOW_ID, whole))
        for n, process in enumerate(knowledge.processes[1:], start=1):
            candidates.append((f"WF-{n:02d}", process))

    index: list[dict] = []
    for workflow_id, process in candidates:
        members = _ordered_actions(process, actions_by_id)
        if not members:
            continue
        title = process.name
        if workflow_id == ALL_WORKFLOW_ID:
            title = f"Entire policy: {process.name}"
        workflow = _workflow_json(
            workflow_id,
            title,
            process.summary,
            process.trigger,
            members,
            knowledge,
            blocks_by_id,
        )
        (output_dir / f"{workflow_id}.json").write_text(
            json.dumps(workflow, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (output_dir / f"{workflow_id}.bpmn").write_bytes(_workflow_bpmn(workflow))
        index.append(
            {
                "workflow_id": workflow_id,
                "title": title,
                "steps": len(workflow["steps"]),
                "gateways": len(workflow["gateways"]),
                "confidence": None,
                "validation_errors": 0,
                "json": f"{workflow_id}.json",
                "bpmn": f"{workflow_id}.bpmn",
            }
        )

    (output_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    (output_dir / "policy_source.html").write_text(_policy_source_html(knowledge), encoding="utf-8")
    return output_dir
