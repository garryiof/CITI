"""policies2BPMN-format workflows (index.json + per-workflow JSON/BPMN) from a pipeline run.

Feeds the offline_p2b viewer pack so it shows the policy that was actually processed,
instead of the static policies2BPMN snapshot.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Optional

from lxml import etree

from policy_knowledge.model.schemas import Action, PolicyKnowledge, Process, SourceBlock

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
NSMAP = {None: BPMN_NS, "bpmndi": BPMNDI_NS, "dc": DC_NS, "di": DI_NS}

UNASSIGNED_ACTOR = "ACT-UNASSIGNED"
ALL_WORKFLOW_ID = "WF-ALL"

_TASK_W, _TASK_H = 130.0, 80.0
_EVENT = 36.0
_COL = 190.0
_ROW = 170.0
_X0, _Y0 = 110.0, 60.0


def _ordered_actions(process: Process, actions_by_id: dict[str, Action]) -> list[Action]:
    return [actions_by_id[a] for a in process.activities if a in actions_by_id]


def _actor_for(action: Action, role_names: dict[str, str]) -> tuple[str, str]:
    for role_id in action.actor_role_ids:
        if role_id in role_names:
            return role_id, role_names[role_id]
    return UNASSIGNED_ACTOR, "Unassigned"


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
        next_id = f"STEP-{idx + 2:03d}" if idx + 1 < len(members) else "END-001"
        steps.append(
            {
                "step_id": f"STEP-{idx + 1:03d}",
                "sequence": idx + 1,
                "title": action.label,
                "description": action.description,
                "actor_id": actor_id,
                "action_type": "MANDATORY_ACTION",
                "bpmn_type": "userTask",
                "source_reference_ids": refs,
                "explicit_or_inferred": "EXPLICIT",
                "canonical_id": action.id,
                "next_step_ids": [next_id],
                "preconditions": list(action.preconditions or []),
                "outputs": list(action.outputs or []),
                "deadline_id": None,
                "exception_ids": [],
                "path_outcome": None,
                "color": None,
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
        "path_outcome": None,
        "color": None,
    }
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
        "gateways": [],
        "events": [start, end],
        "start_event": start,
        "end_events": [end],
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


def _workflow_bpmn(workflow: dict) -> bytes:
    wid = workflow["workflow_id"]
    steps = workflow["steps"]
    actors = workflow["actors"] or [{"actor_id": UNASSIGNED_ACTOR, "name": "Unassigned"}]
    row_of = {a["actor_id"]: i for i, a in enumerate(actors)}

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
    lane_nodes.setdefault(last_actor, []).append("END-001")

    lane_set = _sub(proc, f"{{{BPMN_NS}}}laneSet", id=f"LaneSet_{wid}")
    for actor in actors:
        lane = _sub(lane_set, f"{{{BPMN_NS}}}lane", id=f"Lane_{actor['actor_id']}", name=actor["name"])
        for node_id in lane_nodes.get(actor["actor_id"], []):
            _sub(lane, f"{{{BPMN_NS}}}flowNodeRef").text = node_id

    _sub(proc, f"{{{BPMN_NS}}}startEvent", id="START-001", name=workflow["start_event"]["title"])
    for step in steps:
        _sub(proc, f"{{{BPMN_NS}}}userTask", id=step["step_id"], name=step["title"])
    _sub(proc, f"{{{BPMN_NS}}}endEvent", id="END-001", name="Process completed")

    order = ["START-001", *[s["step_id"] for s in steps], "END-001"]
    flows = []
    for i in range(len(order) - 1):
        flow_id = f"Flow_{i + 1:03d}"
        _sub(proc, f"{{{BPMN_NS}}}sequenceFlow", id=flow_id, sourceRef=order[i], targetRef=order[i + 1])
        flows.append((flow_id, order[i], order[i + 1]))

    actor_of = {"START-001": first_actor, "END-001": last_actor}
    actor_of.update({s["step_id"]: s["actor_id"] for s in steps})
    bounds: dict[str, tuple[float, float, float, float]] = {}
    for col, node_id in enumerate(order):
        is_event = node_id in ("START-001", "END-001")
        w = _EVENT if is_event else _TASK_W
        h = _EVENT if is_event else _TASK_H
        cx = _X0 + col * _COL
        cy = _Y0 + row_of.get(actor_of[node_id], 0) * _ROW + _TASK_H / 2
        bounds[node_id] = (cx - w / 2, cy - h / 2, w, h)

    diagram = _sub(defs, f"{{{BPMNDI_NS}}}BPMNDiagram", id=f"Diagram_{wid}")
    plane = _sub(diagram, f"{{{BPMNDI_NS}}}BPMNPlane", id=f"Plane_{wid}", bpmnElement=f"Process_{wid}")
    for node_id in order:
        x, y, w, h = bounds[node_id]
        shape = _sub(plane, f"{{{BPMNDI_NS}}}BPMNShape", id=f"Shape_{node_id}", bpmnElement=node_id)
        _sub(shape, f"{{{DC_NS}}}Bounds", x=str(x), y=str(y), width=str(w), height=str(h))
    for flow_id, src, tgt in flows:
        sx, sy, sw, sh = bounds[src]
        tx, ty, tw, th = bounds[tgt]
        x1, y1 = sx + sw, sy + sh / 2
        x2, y2 = tx, ty + th / 2
        points = [(x1, y1), (x2, y2)]
        if abs(y1 - y2) > 0.5:
            mid = (x1 + x2) / 2
            points = [(x1, y1), (mid, y1), (mid, y2), (x2, y2)]
        edge = _sub(plane, f"{{{BPMNDI_NS}}}BPMNEdge", id=f"Edge_{flow_id}", bpmnElement=flow_id)
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
                "gateways": 0,
                "confidence": None,
                "validation_errors": 0,
                "json": f"{workflow_id}.json",
                "bpmn": f"{workflow_id}.bpmn",
            }
        )

    (output_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    (output_dir / "policy_source.html").write_text(_policy_source_html(knowledge), encoding="utf-8")
    return output_dir
