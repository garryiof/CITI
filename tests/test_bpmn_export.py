"""BPMN export tests."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from policy_knowledge.exporters.bpmn_exporter import export_bpmn
from policy_knowledge.ingestion import read_policy
from policy_knowledge.intelligence.extraction_pipeline import extract_policy
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM
from policy_knowledge.validation.bpmn_validator import validate_bpmn_dir

FIXTURES = Path(__file__).parent / "fixtures"
NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
}


def test_procedural_bpmn_has_di_and_reachability(tmp_path: Path):
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    knowledge = extract_policy(
        blocks, SyntheticMockLLM(), policy_id="POLICY_001", title="Synthetic Escalation Policy"
    )
    result = export_bpmn(knowledge, tmp_path / "bpmn")
    assert result.bpmn_path is not None
    assert result.no_process_path is None
    xml = result.bpmn_path.read_bytes()
    root = etree.fromstring(xml)
    assert root.xpath("//bpmn:startEvent", namespaces=NS)
    assert root.xpath("//bpmn:endEvent", namespaces=NS)
    assert root.xpath("//bpmndi:BPMNShape", namespaces=NS)
    assert root.xpath("//bpmndi:BPMNEdge", namespaces=NS)
    report = validate_bpmn_dir(tmp_path / "bpmn")
    assert report.ok, report.errors


def test_nonprocedural_emits_no_supported_process(tmp_path: Path):
    blocks = read_policy(FIXTURES / "synthetic_policy_nonprocedural.html")
    knowledge = extract_policy(
        blocks,
        SyntheticMockLLM(mode="nonprocedural"),
        policy_id="POLICY_NP",
        title="Synthetic Principles Policy",
    )
    result = export_bpmn(knowledge, tmp_path / "bpmn")
    assert result.bpmn_path is None
    assert result.no_process_path is not None
    assert result.no_process_path.name == "no_supported_process.json"
    assert not list((tmp_path / "bpmn").glob("*.bpmn"))
