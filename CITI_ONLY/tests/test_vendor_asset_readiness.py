"""Vendor asset readiness checks."""

from __future__ import annotations

from pathlib import Path

from policy_knowledge.exporters.viewer_exporter import check_vendor_readiness

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "src" / "policy_knowledge" / "viewer" / "vendor"


def test_vendor_readiness_fails_without_real_assets():
    report = check_vendor_readiness(VENDOR)
    assert report.interactive_ready is False
    assert report.missing
