"""BPMN 2.0 + DI exporter (or honest no_supported_process)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from policy_knowledge.model.schemas import PolicyKnowledge

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"

NSMAP = {
    None: BPMN_NS,
    "bpmndi": BPMNDI_NS,
    "dc": DC_NS,
    "di": DI_NS,
}


@dataclass
class BPMNExportResult:
    bpmn_path: Path | None
    no_process_path: Path | None
    mappings_path: Path | None
    validation_path: Path | None
    process_index_path: Path | None


def export_bpmn(knowledge: PolicyKnowledge, output_dir: Path) -> BPMNExportResult:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    process = knowledge.processes[0] if knowledge.processes else None
    unsupported = (
        process is None
        or process.modeling_status == "unsupported"
        or not knowledge.actions
    )
    if unsupported:
        no_path = output_dir / "no_supported_process.json"
        no_path.write_text(
            json.dumps(
                {
                    "policy_id": knowledge.policy.id,
                    "reason": "no_defensible_procedure",
                    "modeling_status": getattr(process, "modeling_status", "unsupported"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return BPMNExportResult(
            bpmn_path=None,
            no_process_path=no_path,
            mappings_path=None,
            validation_path=None,
            process_index_path=None,
        )

    definitions = etree.Element(f"{{{BPMN_NS}}}definitions", nsmap=NSMAP)
    definitions.set("id", "Definitions_1")
    definitions.set("targetNamespace", "https://example.local/policy-knowledge")

    collab = etree.SubElement(definitions, f"{{{BPMN_NS}}}collaboration")
    collab.set("id", "Collaboration_1")
    participant = etree.SubElement(collab, f"{{{BPMN_NS}}}participant")
    participant.set("id", "Participant_1")
    participant.set("name", knowledge.policy.title)
    participant.set("processRef", "Process_1")

    process_el = etree.SubElement(definitions, f"{{{BPMN_NS}}}process")
    process_el.set("id", "Process_1")
    process_el.set("isExecutable", "false")
    process_el.set("name", process.name)

    role_by_id = {r.id: r for r in knowledge.roles}
    lane_set = etree.SubElement(process_el, f"{{{BPMN_NS}}}laneSet")
    lane_set.set("id", "LaneSet_1")
    lanes: dict[str, etree._Element] = {}
    default_lane = etree.SubElement(lane_set, f"{{{BPMN_NS}}}lane")
    default_lane.set("id", "Lane_default")
    default_lane.set("name", "Unassigned")
    lanes["default"] = default_lane

    start = etree.SubElement(process_el, f"{{{BPMN_NS}}}startEvent")
    start.set("id", "StartEvent_1")
    start.set("name", "Start")
    etree.SubElement(default_lane, f"{{{BPMN_NS}}}flowNodeRef").text = "StartEvent_1"

    action_ids: list[str] = []
    mappings: dict[str, dict] = {
        "StartEvent_1": {"type": "start", "canonical_ids": [], "source_refs": []},
    }

    for idx, action in enumerate(knowledge.actions):
        task_id = f"Task_{idx+1}"
        task = etree.SubElement(process_el, f"{{{BPMN_NS}}}task")
        task.set("id", task_id)
        task.set("name", action.label)
        action_ids.append(task_id)
        mappings[task_id] = {
            "type": "task",
            "canonical_ids": [action.id, *action.actor_role_ids],
            "source_refs": action.source_refs,
        }
        lane_key = "default"
        if action.actor_role_ids:
            role = role_by_id.get(action.actor_role_ids[0])
            if role:
                lane_key = role.id
                if lane_key not in lanes:
                    lane = etree.SubElement(lane_set, f"{{{BPMN_NS}}}lane")
                    lane.set("id", f"Lane_{idx+1}")
                    lane.set("name", role.name)
                    lanes[lane_key] = lane
        etree.SubElement(lanes[lane_key], f"{{{BPMN_NS}}}flowNodeRef").text = task_id

    end = etree.SubElement(process_el, f"{{{BPMN_NS}}}endEvent")
    end.set("id", "EndEvent_1")
    end.set("name", "End")
    etree.SubElement(default_lane, f"{{{BPMN_NS}}}flowNodeRef").text = "EndEvent_1"
    mappings["EndEvent_1"] = {"type": "end", "canonical_ids": [], "source_refs": []}

    flow_nodes = ["StartEvent_1", *action_ids, "EndEvent_1"]
    for i in range(len(flow_nodes) - 1):
        flow_id = f"Flow_{i+1}"
        flow = etree.SubElement(process_el, f"{{{BPMN_NS}}}sequenceFlow")
        flow.set("id", flow_id)
        flow.set("sourceRef", flow_nodes[i])
        flow.set("targetRef", flow_nodes[i + 1])

    # DI
    diagram = etree.SubElement(definitions, f"{{{BPMNDI_NS}}}BPMNDiagram")
    diagram.set("id", "BPMNDiagram_1")
    plane = etree.SubElement(diagram, f"{{{BPMNDI_NS}}}BPMNPlane")
    plane.set("id", "BPMNPlane_1")
    plane.set("bpmnElement", "Collaboration_1")

    positions: dict[str, tuple[float, float]] = {}
    x = 180.0
    y = 120.0
    for node_id in flow_nodes:
        shape = etree.SubElement(plane, f"{{{BPMNDI_NS}}}BPMNShape")
        shape.set("id", f"{node_id}_di")
        shape.set("bpmnElement", node_id)
        bounds = etree.SubElement(shape, f"{{{DC_NS}}}Bounds")
        width = 36.0 if "Event" in node_id else 100.0
        height = 36.0 if "Event" in node_id else 80.0
        bounds.set("x", str(x))
        bounds.set("y", str(y))
        bounds.set("width", str(width))
        bounds.set("height", str(height))
        positions[node_id] = (x + width / 2, y + height / 2)
        x += 160.0

    for i in range(len(flow_nodes) - 1):
        flow_id = f"Flow_{i+1}"
        edge = etree.SubElement(plane, f"{{{BPMNDI_NS}}}BPMNEdge")
        edge.set("id", f"{flow_id}_di")
        edge.set("bpmnElement", flow_id)
        x1, y1 = positions[flow_nodes[i]]
        x2, y2 = positions[flow_nodes[i + 1]]
        for xx, yy in ((x1, y1), (x2, y2)):
            wp = etree.SubElement(edge, f"{{{DI_NS}}}waypoint")
            wp.set("x", str(xx))
            wp.set("y", str(yy))

    bpmn_path = output_dir / "policy_process.bpmn"
    bpmn_path.write_bytes(
        etree.tostring(definitions, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    )

    mappings_path = output_dir / "activity_mappings.json"
    mappings_path.write_text(json.dumps(mappings, indent=2), encoding="utf-8")

    process_index = output_dir / "process_index.json"
    process_index.write_text(
        json.dumps(
            {
                "process_id": process.id,
                "name": process.name,
                "modeling_status": process.modeling_status,
                "task_count": len(knowledge.actions),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    validation_path = output_dir / "bpmn_validation.json"
    validation_path.write_text(
        json.dumps(
            {
                "well_formed": True,
                "xsd_validated": False,
                "notes": "Well-formedness only; XSD conformity not claimed without schema.",
                "start_end_present": True,
                "di_present": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return BPMNExportResult(
        bpmn_path=bpmn_path,
        no_process_path=None,
        mappings_path=mappings_path,
        validation_path=validation_path,
        process_index_path=process_index,
    )
