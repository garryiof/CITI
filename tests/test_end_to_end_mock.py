"""End-to-end mock pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from policy_knowledge.config import load_config
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM
from policy_knowledge.pipeline import run_policy_demo

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[1]


def test_e2e_mock_builds_isolated_run(tmp_path: Path):
    config = load_config(ROOT / "config" / "app.example.yaml")
    config.workspace.output_root = str(tmp_path / "policy_runs")
    result = run_policy_demo(
        FIXTURES / "synthetic_policy.html",
        policy_id="POLICY_001",
        config=config,
        llm=SyntheticMockLLM(),
        run_id="RUN_TEST_001",
    )
    run_dir = Path(result.run_dir)
    assert run_dir.exists()
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "outputs" / "okf" / "manifest.json").exists()
    assert (run_dir / "outputs" / "bpmn").exists()
    assert (run_dir / "demo" / "index.html").exists()
    assert (run_dir / "outputs" / "canonical" / "role_relevance.json").exists()
    import json

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["llm_provider"] == "mock"
    assert manifest["llm_status"] == "MOCK"
    assert manifest["guardrail_status"] == "GUARDRAIL_NOT_CONNECTED"
    assert "role_relevance" in manifest["artifact_paths"]
    assert result.validation.get("role_relevance", {}).get("ok") is True

    role_doc = json.loads(
        (run_dir / "outputs" / "canonical" / "role_relevance.json").read_text(encoding="utf-8")
    )
    assert set(role_doc["perspectives"].keys()) == {
        "business_owner",
        "compliance_officer",
        "policy_owner",
    }
    data_js = (run_dir / "demo" / "data.js").read_text(encoding="utf-8")
    assert "role_relevance" in data_js
    assert "business_owner" in data_js
    demo_html = (run_dir / "demo" / "index.html").read_text(encoding="utf-8")
    assert "role-select" in demo_html
    assert "Role Intelligence" in demo_html
    demo_app = (run_dir / "demo" / "app.js").read_text(encoding="utf-8")
    assert "fetch(" not in demo_app
    assert "renderIntelligence" in demo_app

    with pytest.raises(FileExistsError):
        run_policy_demo(
            FIXTURES / "synthetic_policy.html",
            policy_id="POLICY_001",
            config=config,
            llm=SyntheticMockLLM(),
            run_id="RUN_TEST_001",
            overwrite=False,
        )

    # overwrite allowed
    again = run_policy_demo(
        FIXTURES / "synthetic_policy.html",
        policy_id="POLICY_001",
        config=config,
        llm=SyntheticMockLLM(),
        run_id="RUN_TEST_001",
        overwrite=True,
    )
    assert Path(again.run_dir) == run_dir
