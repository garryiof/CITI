"""Vendor asset readiness checks."""

from __future__ import annotations

from pathlib import Path

from policy_knowledge.exporters.viewer_exporter import check_vendor_readiness

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "src" / "policy_knowledge" / "viewer" / "vendor"


def test_vendor_readiness_fails_without_real_assets(tmp_path: Path):
    report = check_vendor_readiness(tmp_path)
    assert report.interactive_ready is False
    assert report.missing


def test_vendor_readiness_rejects_stubs():
    report = check_vendor_readiness(VENDOR / "stubs")
    assert report.interactive_ready is False
    assert any("stub" in m for m in report.missing)


def test_vendor_readiness_passes_with_bundled_assets():
    report = check_vendor_readiness(VENDOR)
    assert report.interactive_ready is True, report.missing
