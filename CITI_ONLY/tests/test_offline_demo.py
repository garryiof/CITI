"""Offline demo build + validation."""

from __future__ import annotations

from pathlib import Path

from policy_knowledge.config import TransferPolicy
from policy_knowledge.exporters.viewer_exporter import build_offline_demo
from policy_knowledge.ingestion import read_policy
from policy_knowledge.intelligence.extraction_pipeline import extract_policy
from policy_knowledge.intelligence.role_relevance import analyze_role_relevance
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM
from policy_knowledge.validation.offline_demo_validator import validate_offline_demo

FIXTURES = Path(__file__).parent / "fixtures"


def test_demo_data_js_populated_by_default(tmp_path: Path):
    """Default TransferPolicy embeds full parsed text in data.js for HTML."""
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    knowledge = extract_policy(
        blocks, SyntheticMockLLM(), policy_id="POLICY_001", title="Synthetic Escalation Policy"
    )
    run_dir = tmp_path / "run"
    (run_dir / "outputs" / "bpmn").mkdir(parents=True)
    role_doc = analyze_role_relevance(knowledge, SyntheticMockLLM(), provider="mock")
    demo = build_offline_demo(
        knowledge,
        run_dir,
        transfer_policy=TransferPolicy(),
        role_relevance=role_doc.model_dump(),
    )
    data_js = (demo / "data.js").read_text(encoding="utf-8")
    assert "POLICY_DEMO_DATA" in data_js
    assert "[redacted]" not in data_js
    assert "must escalate exceptions within 1 business day" in data_js.lower()
    assert "role_relevance" in data_js
    assert "why_relevant" in data_js
    report = validate_offline_demo(demo)
    assert report.ok, report.errors
    assert not any("role_relevance" in w for w in report.warnings)

    import json

    manifest = json.loads((demo / "DEMO_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "full_fidelity"
    assert manifest["include_policy_excerpts"] is True


def test_demo_builds_redacted_when_excerpts_disabled(tmp_path: Path):
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    knowledge = extract_policy(
        blocks, SyntheticMockLLM(), policy_id="POLICY_001", title="Synthetic Escalation Policy"
    )
    run_dir = tmp_path / "run"
    (run_dir / "outputs" / "bpmn").mkdir(parents=True)
    demo = build_offline_demo(
        knowledge,
        run_dir,
        transfer_policy=TransferPolicy(include_policy_excerpts_in_demo=False),
    )
    assert (demo / "index.html").exists()
    assert (demo / "data.js").exists()
    assert (demo / "DEMO_MANIFEST.json").exists()
    data_js = (demo / "data.js").read_text(encoding="utf-8")
    assert "POLICY_DEMO_DATA" in data_js
    assert "fetch(" not in (demo / "app.js").read_text(encoding="utf-8")
    report = validate_offline_demo(demo)
    assert report.ok, report.errors
    assert any("interactive" in w.lower() or "BROWSER_TEST" in w for w in report.warnings)

    import json

    manifest = json.loads((demo / "DEMO_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "redacted"
    assert manifest.get("browser_test") == "BROWSER_TEST_NOT_RUN"
    assert manifest["interactive_ready"] is False
    # Redacted mode: no sensitive source passages in embedded demo data
    assert "must escalate exceptions within 1 business day" not in data_js.lower()
    assert "[redacted]" in data_js
