"""BPMN well-formedness checks (not XSD)."""

from __future__ import annotations

import json
from pathlib import Path

from lxml import etree

from policy_knowledge.validation.schema_validator import ValidationReport

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
}


def validate_bpmn_dir(bpmn_dir: Path) -> ValidationReport:
    bpmn_dir = Path(bpmn_dir)
    errors: list[str] = []
    warnings: list[str] = []

    no_process = bpmn_dir / "no_supported_process.json"
    bpmn_files = list(bpmn_dir.glob("*.bpmn"))
    if no_process.exists():
        if bpmn_files:
            errors.append("no_supported_process.json present alongside .bpmn")
        return ValidationReport(ok=not errors, errors=errors, warnings=warnings)

    if not bpmn_files:
        return ValidationReport(ok=False, errors=["no bpmn file and no no_supported_process.json"])

    path = bpmn_files[0]
    try:
        root = etree.parse(str(path)).getroot()
    except etree.XMLSyntaxError as exc:
        return ValidationReport(ok=False, errors=[f"XML not well-formed: {exc}"])

    if not root.xpath("//bpmn:startEvent", namespaces=NS):
        errors.append("missing startEvent")
    if not root.xpath("//bpmn:endEvent", namespaces=NS):
        errors.append("missing endEvent")
    if not root.xpath("//bpmndi:BPMNShape", namespaces=NS):
        errors.append("missing BPMN DI shapes")
    if not root.xpath("//bpmndi:BPMNEdge", namespaces=NS):
        errors.append("missing BPMN DI edges")

    # Reachability: every task appears as source or target of a sequenceFlow
    tasks = {t.get("id") for t in root.xpath("//bpmn:task", namespaces=NS)}
    flows = root.xpath("//bpmn:sequenceFlow", namespaces=NS)
    connected = set()
    for flow in flows:
        connected.add(flow.get("sourceRef"))
        connected.add(flow.get("targetRef"))
    for task_id in tasks:
        if task_id not in connected:
            errors.append(f"task not on sequence flow: {task_id}")

    val_path = bpmn_dir / "bpmn_validation.json"
    if val_path.exists():
        payload = json.loads(val_path.read_text(encoding="utf-8"))
        if payload.get("xsd_validated") is True:
            warnings.append("xsd_validated claimed — confirm schema availability")

    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)
