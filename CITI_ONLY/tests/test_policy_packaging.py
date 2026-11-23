"""Archive + transfer gate tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

from policy_knowledge.config import TransferPolicy, load_config
from policy_knowledge.intelligence.synthetic_mock import SyntheticMockLLM
from policy_knowledge.packaging.package_policy import archive_policy_run
from policy_knowledge.pipeline import run_policy_demo

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[1]


def _run(tmp_path: Path):
    config = load_config(ROOT / "config" / "app.example.yaml")
    config.workspace.output_root = str(tmp_path / "policy_runs")
    return run_policy_demo(
        FIXTURES / "synthetic_policy.html",
        policy_id="POLICY_001",
        config=config,
        llm=SyntheticMockLLM(),
        run_id="RUN_PKG_001",
        overwrite=True,
    )


def test_transfer_gate_blocks_demo_by_default(tmp_path: Path):
    result = _run(tmp_path)
    archives = archive_policy_run(result.run_dir, TransferPolicy())
    assert archives.demo_zip is None
    assert archives.full_zip is None
    assert archives.report_path.exists()
    assert not list((result.run_dir / "archive").glob("*_FULL.zip"))


def test_demo_zip_when_transfer_approved_redacted(tmp_path: Path):
    result = _run(tmp_path)
    policy = TransferPolicy(
        workstation_transfer_approved=True,
        include_policy_excerpts_in_demo=False,
    )
    archives = archive_policy_run(result.run_dir, policy)
    assert archives.demo_zip is not None
    with zipfile.ZipFile(archives.demo_zip) as zf:
        names = zf.namelist()
        assert any(n.endswith("index.html") for n in names)
        assert all(n.startswith("demo/") or n == "demo/" or "/" not in n.rstrip("/") for n in names) or all(
            "demo" in n or n.endswith(".html") or n.endswith(".js") or n.endswith(".css") or n.endswith(".json")
            for n in names
        )
        # DEMO ZIP should contain demo tree only
        assert all(not n.startswith("outputs/") for n in names)
        assert zf.testzip() is None


def test_spaces_in_extract_path(tmp_path: Path):
    result = _run(tmp_path)
    policy = TransferPolicy(workstation_transfer_approved=True)
    archives = archive_policy_run(result.run_dir, policy)
    extract_dir = tmp_path / "path with spaces" / "out"
    extract_dir.mkdir(parents=True)
    with zipfile.ZipFile(archives.demo_zip) as zf:
        zf.extractall(extract_dir)
    assert list(extract_dir.rglob("index.html"))
