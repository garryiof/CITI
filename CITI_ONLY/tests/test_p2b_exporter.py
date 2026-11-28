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
        input_path=str(FIXTURES / "synthetic_policy.html"),
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
    assert "source_file" not in payload
    assert "synthetic_policy.html" not in (out / "index.html").read_text(encoding="utf-8")
    assert "function policyId()" in (out / "app.js").read_text(encoding="utf-8")
    css = (out / "styles.css").read_text(encoding="utf-8")
    assert "height: 74px;" in css


def test_export_emits_decision_gateway_and_rejected_branch(tmp_path: Path):
    from policy_knowledge.model.schemas import Decision

    knowledge = _knowledge()
    ref = knowledge.actions[0].source_refs[0]
    next_label = knowledge.actions[1].label if len(knowledge.actions) > 1 else ""
    knowledge.decisions = [
        Decision(
            id="DEC-APPROVAL-1",
            question="Is the request approved and transaction permitted?",
            branches=[
                {"condition": "Approved", "outcome": "PROCEED", "next_action_label": next_label},
                {
                    "condition": "Rejected / Prohibited",
                    "outcome": "PROHIBITED",
                    "next_action_label": None,
                    "end_label": "Must not proceed — prohibited or rejected",
                },
            ],
            source_refs=[ref],
        )
    ]
    out_dir = export_p2b_workflows(knowledge, tmp_path / "p2b")
    index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
    wf_all = next(i for i in index if i["workflow_id"] == "WF-ALL")
    assert wf_all["gateways"] == 1

    wf_json = json.loads((out_dir / "WF-ALL.json").read_text(encoding="utf-8"))
    assert len(wf_json["gateways"]) == 1
    assert any(e["event_id"] == "END-REJ-001" for e in wf_json["end_events"])

    xml = etree.fromstring((out_dir / "WF-ALL.bpmn").read_bytes())
    gws = xml.findall(f".//{BPMN_NS}exclusiveGateway")
    assert len(gws) == 1
    assert gws[0].get("name") == "Is the request approved and transaction permitted?"
    end_ids = {e.get("id") for e in xml.findall(f".//{BPMN_NS}endEvent")}
    assert {"END-001", "END-REJ-001"} <= end_ids
    flow_names = {f.get("name") for f in xml.findall(f".//{BPMN_NS}sequenceFlow") if f.get("name")}
    assert {"Approved", "Rejected / Prohibited"} <= flow_names


def test_derive_role_workflow_map_differentiates_roles():
    from build_offline_p2b import derive_role_workflow_map

    workflows = {
        "WF-ALL": {"json": {"steps": [{"canonical_id": "ACT-1", "source_reference_ids": ["B1"]}, {"canonical_id": "ACT-2", "source_reference_ids": ["B2"]}]}},
        "WF-01": {"json": {"steps": [{"canonical_id": "ACT-1", "source_reference_ids": ["B1"]}]}},
        "WF-02": {"json": {"steps": [{"canonical_id": "ACT-2", "source_reference_ids": ["B2"]}]}},
    }
    rr = {
        "perspectives": {
            "business_owner": {
                "assessments": [
                    {
                        "artifact_id": "ACT-1",
                        "artifact_type": "action",
                        "relevance": "PRIMARY",
                        "why_relevant": "Follower must pre-clear.",
                        "lens_tags": ["required_action", "deadline_or_approval"],
                        "source_refs": ["B1"],
                    }
                ]
            },
            "compliance_officer": {
                "assessments": [
                    {
                        "artifact_id": "CTL-1",
                        "artifact_type": "control",
                        "relevance": "PRIMARY",
                        "why_relevant": "Compliance tests violation control.",
                        "lens_tags": ["control_verification"],
                        "associated_action_ids": ["ACT-2"],
                        "associated_control_ids": ["CTL-1"],
                        "source_refs": ["B2"],
                    }
                ]
            },
            "policy_owner": {
                "assessments": [
                    {
                        "artifact_id": "FIND-1",
                        "artifact_type": "finding",
                        "relevance": "PRIMARY",
                        "why_relevant": "Owner must close governance gap.",
                        "lens_tags": ["ambiguity_or_gap"],
                        "source_refs": ["B1"],
                    }
                ]
            },
        }
    }
    rmap = derive_role_workflow_map(rr, workflows)
    assert [e["workflow_id"] for e in rmap["business_owner"]] == ["WF-01"]
    assert [e["workflow_id"] for e in rmap["compliance_officer"]] == ["WF-02"]
    assert "WF-ALL" in [e["workflow_id"] for e in rmap["policy_owner"]]



def test_risk_catalog_labels_and_taxonomy_summary():
    from build_offline_p2b import build_canonical_catalog, risk_taxonomy_summary

    knowledge = {
        "risks": [
            {"id": "R1", "name": "Delayed escalation", "risk_code": "RISK_OPS",
             "risk_label": "Operational Risk", "classification_origin": "normalized", "source_refs": ["B1"]},
            {"id": "R2", "name": "Missed attestation", "risk_code": "RISK_CONDUCT",
             "risk_label": "Conduct Risk", "classification_origin": "suggested", "source_refs": ["B1"]},
            {"id": "R3", "name": "Unclear exposure", "risk_code": None,
             "risk_label": None, "classification_origin": "source_stated", "source_refs": ["B2"]},
        ]
    }
    catalog = build_canonical_catalog(knowledge)
    assert catalog["R1"]["label"] == "RISK_OPS · Operational Risk"
    assert catalog["R1"]["policy_wording"] == "Delayed escalation"
    assert catalog["R2"]["classification_origin"] == "suggested"
    assert catalog["R3"]["label"] == "Unmapped: Unclear exposure"
    assert catalog["R3"]["unmapped"] is True

    summary = risk_taxonomy_summary(catalog)
    assert summary == {"total": 3, "mapped": 1, "suggested": 1, "unmapped": 1}


def test_risk_control_csv_has_risk_code_column():
    from policy_knowledge.governance.risk_control_matrix import build_risk_control_rows

    knowledge = _knowledge()
    knowledge.risks[0].risk_code = "RISK_OPS"
    rows = build_risk_control_rows(knowledge)
    assert rows[0]["risk_code"] == "RISK_OPS"
    assert all("risk_code" in row for row in rows)
    assert any(row["risk_code"] == "unmapped" for row in rows[1:]) or len(rows) == 1


def test_offline_pack_ships_risk_chip_and_overview_code(tmp_path: Path):
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
    data = (out / "data.js").read_text(encoding="utf-8")
    payload = json.loads(data[len("window.P2B_DATA = ") : -2])
    assert payload["risk_taxonomy"]["total"] == len(knowledge.risks)
    assert payload["risk_taxonomy"]["unmapped"] == len(knowledge.risks)

    app_js = (out / "app.js").read_text(encoding="utf-8")
    assert "is-unmapped" in app_js and "renderRiskTaxonomyNote" in app_js
    css = (out / "styles.css").read_text(encoding="utf-8")
    assert ".intel-chip-risk.is-unmapped" in css and ".intel-chip-risk.is-suggested" in css


def test_match_decisions_prevents_cross_topic_gateway_collision(tmp_path: Path):
    from policy_knowledge.model.schemas import Action, Decision, Policy, PolicyKnowledge, Process, Role, SourceBlock

    b1 = SourceBlock(
        id="SRC-0007",
        policy_id="PTIP",
        section_path="PDF page 7",
        text="Covered Persons must obtain ICRM approval for Reportable Accounts and obtain pre-clearance to trade a security.",
        block_type="page",
        source_locator="pdf:page[7]",
        sequence=1,
        document_hash="h",
    )
    r1 = Role(id="ROLE-1", name="Covered Person", source_refs=["SRC-0007"])
    a1 = Action(
        id="ACT-1",
        label="Obtain ICRM approval for new Reportable Accounts",
        description="Obtain ICRM approval prior to opening a new Reportable Account.",
        actor_role_ids=["ROLE-1"],
        source_refs=["SRC-0007"],
    )
    a2 = Action(
        id="ACT-2",
        label="Disclose Reportable Accounts",
        description="Disclose Reportable Accounts in the compliance system.",
        actor_role_ids=["ROLE-1"],
        source_refs=["SRC-0007"],
    )
    a3 = Action(
        id="ACT-3",
        label="Submit pre-clearance request",
        description="Submit pre-clearance request before trading a particular security.",
        actor_role_ids=["ROLE-1"],
        source_refs=["SRC-0007"],
    )
    a4 = Action(
        id="ACT-4",
        label="Execute security trade",
        description="Execute the approved security transaction.",
        actor_role_ids=["ROLE-1"],
        source_refs=["SRC-0007"],
    )
    dec = Decision(
        id="DEC-1",
        question="Is the Covered Person eligible to trade in a particular security?",
        branches=[
            {"condition": "Approved", "outcome": "PROCEED", "next_action_label": None},
            {"condition": "Rejected / Prohibited", "outcome": "PROHIBITED", "next_action_label": None},
        ],
        source_refs=["SRC-0007"],
    )
    knowledge = PolicyKnowledge(
        policy=Policy(id="PTIP", title="Personal Trading", input_path="p.pdf", source_hash="h", review_status="extracted"),
        source_blocks=[b1],
        roles=[r1],
        actions=[a1, a2, a3, a4],
        decisions=[dec],
        processes=[
            Process(id="P-ALL", name="All", activities=["ACT-1", "ACT-2", "ACT-3", "ACT-4"], source_refs=["SRC-0007"], modeling_status="supported"),
            Process(id="P-ACC", name="Reportable Accounts", activities=["ACT-1", "ACT-2"], source_refs=["SRC-0007"], modeling_status="supported"),
            Process(id="P-TRD", name="Security Trading", activities=["ACT-3", "ACT-4"], source_refs=["SRC-0007"], modeling_status="supported"),
        ],
    )
    out = export_p2b_workflows(knowledge, tmp_path / "p2b")
    acc = json.loads((out / "WF-01.json").read_text(encoding="utf-8"))
    trd = json.loads((out / "WF-02.json").read_text(encoding="utf-8"))
    # Reportable Accounts must NOT receive the security-trading eligibility gateway.
    assert acc["gateways"][0]["question"] != dec.question
    assert acc["gateways"][0]["explicit_or_inferred"] == "INFERRED"
    # Security Trading DOES receive the security-trading eligibility gateway.
    assert trd["gateways"][0]["question"] == dec.question
    assert trd["gateways"][0]["explicit_or_inferred"] == "EXPLICIT"


def test_role_steps_json_and_offline_embed(tmp_path: Path):
    from build_offline_p2b import build_offline_p2b, build_role_workflow_map
    from policy_knowledge.exporters.role_steps_exporter import export_role_steps

    # Static snapshot map includes PTP-BLK under business_owner for full follower coverage.
    static_map = build_role_workflow_map([
        {"workflow_id": "PTP-PRECLEAR"},
        {"workflow_id": "PTP-BLK"},
        {"workflow_id": "PTP-VIOL"},
        {"workflow_id": "PTP-POLICY"},
    ])
    assert any(e["workflow_id"] == "PTP-BLK" for e in static_map["business_owner"])

    knowledge = _knowledge()
    run_dir = tmp_path / "run"
    p2b_dir = export_p2b_workflows(knowledge, run_dir / "outputs" / "p2b")
    canonical = run_dir / "outputs" / "canonical"
    canonical.mkdir(parents=True)
    role_doc = analyze_role_relevance(knowledge, SyntheticMockLLM(), provider="mock")
    export_role_relevance(role_doc, canonical / "role_relevance.json")
    (canonical / "policy_knowledge.json").write_text(knowledge.model_dump_json(), encoding="utf-8")

    rs_path = export_role_steps(
        p2b_dir,
        role_doc.model_dump(),
        canonical / "role_steps.json",
        policy_id=knowledge.policy.id,
        policy_title=knowledge.policy.title,
    )
    rs_doc = json.loads(rs_path.read_text(encoding="utf-8"))
    assert rs_doc["schema_version"] == "role_steps-1.0"
    assert set(rs_doc["roles"]) == {"business_owner", "compliance_officer", "policy_owner"}
    assert rs_doc["roles"]["business_owner"]["total_steps"] > 0
    first_step = rs_doc["roles"]["business_owner"]["steps"][0]
    assert {"order", "workflow_id", "workflow_title", "step_id", "title", "description", "actor", "role_guidance"} <= set(first_step)

    out = build_offline_p2b(REPO_ROOT, tmp_path / "pack", canonical_run_dir=run_dir)
    assert (out / "role_steps.json").is_file()
    manifest = json.loads((out / "OFFLINE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["role_steps_embedded"] is True
    data = (out / "data.js").read_text(encoding="utf-8")
    payload = json.loads(data[len("window.P2B_DATA = ") : -2])
    assert set(payload["role_steps"]["roles"]) == {"business_owner", "compliance_officer", "policy_owner"}
    role_js = (out / "role_intelligence.js").read_text(encoding="utf-8")
    assert "downloadRoleStepsJson" in role_js
    assert "Workflow steps in order" in role_js
    assert "Policy process steps in order" in role_js

