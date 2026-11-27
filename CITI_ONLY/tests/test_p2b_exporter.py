"""Run-generated policies2BPMN workflows (Pass W + p2b exporter + offline pack)."""

from __future__ import annotations

import json
from pathlib import Path

from lxml import etree

from policy_knowledge.exporters.p2b_exporter import export_p2b_workflows
from policy_knowledge.ingestion import read_policy
from policy_knowledge.intelligence.extraction_pipeline import extract_policy
from policy_knowledge.intelligence.pass_schemas import PassWResult
from policy_knowledge.intelligence.role_relevance import (
    analyze_role_relevance,
    export_role_relevance,
)
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[1]
BPMN_NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"


def _knowledge(llm=None):
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    return extract_policy(
        blocks,
        llm or SyntheticMockLLM(),
        policy_id="POLICY_001",
        title="Synthetic Escalation Policy",
    )


class _NoGroupingLLM(SyntheticMockLLM):
    def parse_structured(self, messages, schema, **kwargs):
        if schema is PassWResult:
            raise RuntimeError("grouping unavailable")
        return super().parse_structured(messages, schema, **kwargs)


def test_pass_w_adds_workflow_processes():
    knowledge = _knowledge()
    assert len(knowledge.processes) == 3
    whole, first, second = knowledge.processes
    assert first.name == "Escalate an exception"
    assert first.activities == whole.activities[:-1]
    assert second.activities == whole.activities[-1:]
    assert first.trigger == "An exception is identified."


def test_pass_w_failure_keeps_whole_policy_workflow(tmp_path: Path):
    knowledge = _knowledge(_NoGroupingLLM())
    assert len(knowledge.processes) == 1
    assert any(f.category == "workflow_grouping_failed" for f in knowledge.findings)
    index = json.loads((export_p2b_workflows(knowledge, tmp_path) / "index.json").read_text())
    assert [i["workflow_id"] for i in index] == ["WF-ALL"]


def test_export_writes_consistent_json_bpmn_and_anchors(tmp_path: Path):
    knowledge = _knowledge()
    out = export_p2b_workflows(knowledge, tmp_path / "p2b")
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert [i["workflow_id"] for i in index] == ["WF-ALL", "WF-01", "WF-02"]

    source_html = (out / "policy_source.html").read_text(encoding="utf-8")
    action_ids = {a.id for a in knowledge.actions}
    for item in index:
        wf = json.loads((out / item["json"]).read_text(encoding="utf-8"))
        assert wf["steps"] and item["steps"] == len(wf["steps"])
        assert {s["canonical_id"] for s in wf["steps"]} <= action_ids
        assert wf["steps"][-1]["next_step_ids"] == ["END-001"]

        tree = etree.fromstring((out / item["bpmn"]).read_bytes())
        tasks = [t.get("id") for t in tree.iter(f"{BPMN_NS}userTask")]
        assert tasks == [s["step_id"] for s in wf["steps"]]
        shapes = {s.get("bpmnElement") for s in tree.iter("{http://www.omg.org/spec/BPMN/20100524/DI}BPMNShape")}
        assert {"START-001", "END-001", *tasks} <= shapes

        for ref in wf["source_references"]:
            assert f'id="{ref["anchor"]}"' in source_html


def test_offline_pack_uses_run_workflows(tmp_path: Path):
    from build_offline_p2b import build_offline_p2b

    knowledge = _knowledge()
    run_dir = tmp_path / "run"
    export_p2b_workflows(knowledge, run_dir / "outputs" / "p2b")
    canonical = run_dir / "outputs" / "canonical"
    canonical.mkdir(parents=True)
    role_doc = analyze_role_relevance(knowledge, SyntheticMockLLM(), provider="mock")
    export_role_relevance(role_doc, canonical / "role_relevance.json")
    (canonical / "policy_knowledge.json").write_text(knowledge.model_dump_json(), encoding="utf-8")

    out = build_offline_p2b(REPO_ROOT, tmp_path / "pack", canonical_run_dir=run_dir)
    manifest = json.loads((out / "OFFLINE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["workflow_source"] == "pipeline_run"
    assert manifest["workflow_count"] == 3

    data = (out / "data.js").read_text(encoding="utf-8")
    payload = json.loads(data[len("window.P2B_DATA = ") : -2])
    assert set(payload["workflows"]) == {"WF-ALL", "WF-01", "WF-02"}
    assert "PTP-" not in data
    role_map = payload["role_workflow_map"]
    assert all(role_map[r] for r in ("business_owner", "compliance_officer", "policy_owner"))
    known = set(payload["workflows"])
    assert all(e["workflow_id"] in known for entries in role_map.values() for e in entries)
