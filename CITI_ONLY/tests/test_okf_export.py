"""OKF export + taxonomy mapping tests."""

from __future__ import annotations

from pathlib import Path

from policy_knowledge.governance.taxonomy_mapper import map_role_label
from policy_knowledge.ingestion import read_policy
from policy_knowledge.intelligence.extraction_pipeline import extract_policy
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM
from policy_knowledge.exporters.okf_exporter import export_okf
from policy_knowledge.exporters.matrix_exporter import export_matrices
from policy_knowledge.validation.okf_validator import validate_okf

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[1]


def _knowledge():
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    return extract_policy(
        blocks,
        SyntheticMockLLM(),
        policy_id="POLICY_001",
        title="Synthetic Escalation Policy",
        input_path=str(FIXTURES / "synthetic_policy.html"),
    )


def test_okf_manifest_frontmatter_and_links(tmp_path: Path):
    knowledge = _knowledge()
    paths = export_okf(knowledge, tmp_path / "okf")
    assert any(p.name == "manifest.json" for p in paths)
    report = validate_okf(tmp_path / "okf")
    assert report.ok, report.errors
    policy_md = (tmp_path / "okf" / "policy.md").read_text(encoding="utf-8")
    assert "review_status:" in policy_md
    assert "id:" in policy_md


def test_taxonomy_exact_alias_unknown():
    tax = ROOT / "config" / "role_taxonomy.yaml"
    assert map_role_label("Policy Owner", tax).status == "exact"
    assert map_role_label("document owner", tax).status == "alias"
    assert map_role_label("Space Cadet", tax).status == "unmapped"


def test_matrices_exported(tmp_path: Path):
    knowledge = _knowledge()
    out = export_matrices(knowledge, tmp_path / "matrices")
    assert (out / "role_matrix.csv").exists()
    assert (out / "risk_control_matrix.csv").exists()
    assert (out / "traceability.csv").exists()
