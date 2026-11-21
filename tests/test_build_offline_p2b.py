"""Offline policies2BPMN-style pack builder."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_rmtree_uses_python311_compatible_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Python 3.11 has onerror; onexc was added in 3.12 (notebook Cell 10 failure mode)."""
    from build_offline_p2b import _rmtree

    target = tmp_path / "to_remove"
    target.mkdir()
    (target / "f.txt").write_text("x", encoding="utf-8")

    seen: dict[str, object] = {}
    real_rmtree = shutil.rmtree

    def fake_rmtree(path, **kwargs):  # noqa: ANN001
        seen["path"] = path
        seen["kwargs"] = kwargs
        real_rmtree(path)

    monkeypatch.setattr(shutil, "rmtree", fake_rmtree)
    _rmtree(target)

    assert not target.exists()
    if sys.version_info >= (3, 12):
        assert "onexc" in seen["kwargs"]
        assert "onerror" not in seen["kwargs"]
    else:
        assert "onerror" in seen["kwargs"]
        assert "onexc" not in seen["kwargs"]


def test_build_offline_p2b_writes_required_files(tmp_path: Path):
    from build_offline_p2b import build_offline_p2b

    out = build_offline_p2b(REPO_ROOT, tmp_path / "offline_p2b")
    for name in ("index.html", "app.js", "styles.css", "data.js", "policy_source.html"):
        assert (out / name).is_file(), name
    assert (out / "vendor" / "bpmn-modeler.production.min.js").is_file()
    data = (out / "data.js").read_text(encoding="utf-8")
    assert "window.P2B_DATA" in data
    assert "PTP-PRECLEAR" in data or "PTP-POLICY" in data
    assert "fetch(" not in (out / "app.js").read_text(encoding="utf-8")


def test_build_offline_p2b_fails_without_modeler_umd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from build_offline_p2b import build_offline_p2b

    fake_root = tmp_path / "repo"
    # Minimal fake tree: outputs exist, but no bpmn-js dist modeler.
    outputs = fake_root / "policies2BPMN" / "outputs"
    outputs.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "policies2BPMN" / "outputs" / "index.json", outputs / "index.json")
    (outputs / "policy_source.html").write_text("<html></html>", encoding="utf-8")
    # Copy one tiny workflow pair so index resolution does not fail first.
    index = (outputs / "index.json").read_text(encoding="utf-8")
    import json

    items = json.loads(index)
    wid = items[0]["workflow_id"]
    src = REPO_ROOT / "policies2BPMN" / "outputs"
    shutil.copy2(src / f"{wid}.json", outputs / f"{wid}.json")
    shutil.copy2(src / f"{wid}.bpmn", outputs / f"{wid}.bpmn")
    # Point index at only that one workflow so we don't need all files.
    (outputs / "index.json").write_text(
        json.dumps([{**items[0], "json": f"{wid}.json", "bpmn": f"{wid}.bpmn"}]),
        encoding="utf-8",
    )

    assets = fake_root / "notebooks" / "offline_p2b_assets"
    assets.mkdir(parents=True)
    for name, body in (
        ("index.html", "<html></html>"),
        ("app.js", "/* P2B_DATA */"),
        ("styles.css", "body{}"),
        ("role_intelligence.html", "<html></html>"),
        ("role_intelligence.js", "/* role */"),
    ):
        (assets / name).write_text(body, encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="bpmn-modeler"):
        build_offline_p2b(fake_root, tmp_path / "out")


def test_offline_assets_reference_p2b_data_and_no_fetch():
    app = (REPO_ROOT / "notebooks" / "offline_p2b_assets" / "app.js").read_text(encoding="utf-8")
    assert "P2B_DATA" in app
    assert "fetch(" not in app
    assert "Side-by-side compare" in app
    assert "localStorage" in app
    assert "policy_source.html#" in app
    # Element clicks must patch the detail pane without wiping the BPMN canvas.
    assert "function patchDetail" in app
    assert "patchDetail();" in app
    # Review access stays distinct from intelligence lenses (UI hidden for now).
    assert "SHOW_REVIEW_ACCESS" in app
    assert "Review access" in app
    assert "Intelligence lens" in app
    assert "All roles (main view)" in app
    assert "Personal Trading Policy" in app
    assert "BlackRock" not in app
    assert "main_view" in app
    assert 'return "main_view"' in app
    assert "isRoleLens" in app
    assert "role_intelligence.html?lens=" in app
    assert "openRoleIntelligenceTab" in app
    assert "window.open" in app
    assert "p2b-user-role" in app
    assert "p2b-intelligence-lens" in app
    assert "business_owner" in app
    assert "Policy Follower" in app
    assert "compliance_officer" in app
    assert "hasRoleRelevance" in app
    assert "renderIntelligenceOverlay" in app
    assert "toggle-intel" in app
    # Main view must not open a role tab.
    assert 'if (isRoleLens(lens)) {\n      openRoleIntelligenceTab(lens);' in app or (
        "if (isRoleLens(lens))" in app and "openRoleIntelligenceTab(lens)" in app
    )
    role_page = (
        REPO_ROOT / "notebooks" / "offline_p2b_assets" / "role_intelligence.js"
    ).read_text(encoding="utf-8")
    assert "Policy Follower" in role_page
    assert "Personal Trading Policy" in role_page
    assert "HEURISTIC_MAP" in role_page
    assert "PTP-PRECLEAR" in role_page
    assert "role-bpmn-canvas" in role_page
    assert "mountBpmn" in role_page
    assert "data-select-workflow" in role_page
    assert "BlackRock" not in role_page
    assert "MCO" not in role_page
    assert "role-workspace" in role_page
    assert "role-rail" in role_page
    assert "role-detail" in role_page
    assert "policyTitle" in role_page
    assert "role-intel-role-badge" in role_page
    assert 'data-action="set-lens"' not in role_page
    assert "<select" not in role_page
    assert 'main_view:' not in role_page
    assert 'main_view: "All roles' not in role_page
    assert "URLSearchParams" in role_page
    assert "fetch(" not in role_page
    # Guard against quote-broken HTML fragments that blank the role tab.
    assert '"</span><span class="role-diagram-node-label">' not in role_page
    role_html = (
        REPO_ROOT / "notebooks" / "offline_p2b_assets" / "role_intelligence.html"
    ).read_text(encoding="utf-8")
    assert "data.js" in role_html
    assert "role_intelligence.js" in role_html
    assert "bpmn-modeler.production.min.js" in role_html
    from build_offline_p2b import build_role_workflow_map
    sample_map = build_role_workflow_map(
        [{"workflow_id": "PTP-PRECLEAR"}, {"workflow_id": "PTP-VIOL"}, {"workflow_id": "PTP-POLICY"}]
    )
    assert sample_map["business_owner"][0]["workflow_id"] == "PTP-PRECLEAR"
    assert sample_map["compliance_officer"][0]["workflow_id"] == "PTP-VIOL"
    assert sample_map["policy_owner"][0]["workflow_id"] == "PTP-POLICY"
    assert 'data-action="set-lens"' not in role_html
    import subprocess

    check = subprocess.run(
        ["node", "--check", str(REPO_ROOT / "notebooks" / "offline_p2b_assets" / "role_intelligence.js")],
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stderr
    check_app = subprocess.run(
        ["node", "--check", str(REPO_ROOT / "notebooks" / "offline_p2b_assets" / "app.js")],
        capture_output=True,
        text=True,
    )
    assert check_app.returncode == 0, check_app.stderr


def test_build_canonical_catalog_maps_entities():
    from build_offline_p2b import build_canonical_catalog

    catalog = build_canonical_catalog(
        {
            "requirements": [
                {"id": "REQ-1", "text": "Must escalate", "source_refs": ["SRC-1"]}
            ],
            "actions": [{"id": "ACT-1", "label": "Escalate", "source_refs": ["SRC-1"]}],
            "source_blocks": [
                {
                    "id": "SRC-1",
                    "text": "Analysts must escalate within five business days.",
                    "source_locator": "html:#s3-p1",
                    "section_path": "3. Requirements",
                }
            ],
        }
    )
    assert catalog["REQ-1"]["type"] == "requirement"
    assert catalog["REQ-1"]["label"] == "Must escalate"
    assert catalog["ACT-1"]["label"] == "Escalate"
    assert catalog["SRC-1"]["type"] == "source"
    assert "five business days" in catalog["SRC-1"]["label"]


def test_build_offline_p2b_omits_role_relevance_by_default(tmp_path: Path):
    from build_offline_p2b import build_offline_p2b

    out = build_offline_p2b(REPO_ROOT, tmp_path / "offline_legacy")
    data = (out / "data.js").read_text(encoding="utf-8")
    assert "window.P2B_DATA" in data
    assert '"role_relevance"' not in data
    manifest = json.loads((out / "OFFLINE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest.get("role_relevance_embedded") is False


def test_build_offline_p2b_embeds_role_relevance(tmp_path: Path):
    from build_offline_p2b import build_offline_p2b

    run_dir = tmp_path / "run"
    canonical = run_dir / "outputs" / "canonical"
    canonical.mkdir(parents=True)
    role_doc = {
        "schema_version": "role_relevance-1.0",
        "policy_id": "SYNTH_001",
        "generated_at": "2026-11-20T00:00:00+00:00",
        "prompt": {},
        "llm": {},
        "perspectives": {
            "business_owner": {
                "assessments": [
                    {
                        "artifact_id": "REQ-1",
                        "artifact_type": "requirement",
                        "relevance": "PRIMARY",
                        "why_relevant": "Operational deadline",
                        "interpretation_basis": "explicit",
                        "source_refs": ["SRC-1"],
                        "associated_action_ids": ["ACT-1"],
                        "associated_risk_ids": [],
                        "associated_control_ids": [],
                        "associated_evidence_ids": [],
                        "lens_tags": ["deadline_or_approval"],
                    }
                ]
            },
            "compliance_officer": {"assessments": []},
            "policy_owner": {"assessments": []},
        },
    }
    knowledge = {
        "requirements": [
            {"id": "REQ-1", "text": "Escalate in five business days", "source_refs": ["SRC-1"]}
        ],
        "actions": [{"id": "ACT-1", "label": "Escalate", "source_refs": ["SRC-1"]}],
        "roles": [],
        "decisions": [],
        "risks": [],
        "controls": [],
        "evidence": [],
        "findings": [],
        "source_blocks": [
            {
                "id": "SRC-1",
                "text": "Escalate within five business days.",
                "source_locator": "html:#s3",
                "section_path": "3",
            }
        ],
    }
    (canonical / "role_relevance.json").write_text(
        json.dumps(role_doc), encoding="utf-8"
    )
    (canonical / "policy_knowledge.json").write_text(
        json.dumps(knowledge), encoding="utf-8"
    )

    out = build_offline_p2b(
        REPO_ROOT,
        tmp_path / "offline_with_lens",
        canonical_run_dir=run_dir,
    )
    data = (out / "data.js").read_text(encoding="utf-8")
    assert '"role_relevance"' in data
    assert '"canonical_catalog"' in data
    assert "REQ-1" in data
    assert "business_owner" in data
    manifest = json.loads((out / "OFFLINE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest.get("role_relevance_embedded") is True
    # Assets must still be classic scripts with no network.
    assert "fetch(" not in (out / "app.js").read_text(encoding="utf-8")


def test_load_role_intelligence_skips_invalid_json(tmp_path: Path):
    from build_offline_p2b import load_role_intelligence

    bad = tmp_path / "role_relevance.json"
    bad.write_text("{not-json", encoding="utf-8")
    rr, catalog = load_role_intelligence(role_relevance_path=bad)
    assert rr is None
    assert catalog is None


def test_build_role_workflow_map_and_zip_offline_pack(tmp_path: Path):
    import zipfile

    from build_offline_p2b import build_role_workflow_map, zip_offline_pack

    index = [
        {"workflow_id": "PTP-PRECLEAR"},
        {"workflow_id": "PTP-VIOL"},
        {"workflow_id": "PTP-POLICY"},
    ]
    mapping = build_role_workflow_map(index)
    assert mapping["business_owner"][0]["workflow_id"] == "PTP-PRECLEAR"
    assert mapping["compliance_officer"][0]["workflow_id"] == "PTP-VIOL"
    assert mapping["policy_owner"][0]["workflow_id"] == "PTP-POLICY"

    pack = tmp_path / "offline_p2b"
    pack.mkdir()
    (pack / "index.html").write_text("<html></html>", encoding="utf-8")
    (pack / "app.js").write_text("/* app */", encoding="utf-8")
    (pack / "role_intelligence.html").write_text("<html></html>", encoding="utf-8")
    (pack / "README_OFFLINE.txt").write_text("readme", encoding="utf-8")
    vendor = pack / "vendor"
    vendor.mkdir()
    (vendor / "bpmn-modeler.production.min.js").write_text("/* bpmn */", encoding="utf-8")

    zpath = zip_offline_pack(pack, tmp_path / "demo.zip")
    assert zpath.is_file()
    with zipfile.ZipFile(zpath) as zf:
        names = set(zf.namelist())
    assert "offline_p2b/index.html" in names
    assert "offline_p2b/role_intelligence.html" in names
    assert "offline_p2b/vendor/bpmn-modeler.production.min.js" in names


def test_build_uses_assets_vendor_without_node_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Lean packs rebuild from offline_p2b_assets/vendor when node_modules is absent."""
    import build_offline_p2b as mod
    from build_offline_p2b import build_offline_p2b

    assets_modeler = (
        REPO_ROOT
        / "notebooks"
        / "offline_p2b_assets"
        / "vendor"
        / "bpmn-modeler.production.min.js"
    )
    assert assets_modeler.is_file()

    real_is_file = Path.is_file
    real_is_dir = Path.is_dir

    def is_file_no_nm(self: Path) -> bool:
        if "/node_modules/" in str(self).replace("\\", "/"):
            return False
        return real_is_file(self)

    def is_dir_no_nm(self: Path) -> bool:
        if "/node_modules/" in str(self).replace("\\", "/"):
            return False
        return real_is_dir(self)

    monkeypatch.setattr(Path, "is_file", is_file_no_nm)
    monkeypatch.setattr(Path, "is_dir", is_dir_no_nm)

    assert mod._modeler_umd(REPO_ROOT) == assets_modeler
    out = build_offline_p2b(REPO_ROOT, tmp_path / "offline_p2b")
    assert (out / "vendor" / "bpmn-modeler.production.min.js").is_file()
    assert (out / "vendor" / "bpmn-js.css").is_file()


def test_offline_zip_contains_role_and_main_entrypoints(tmp_path: Path):
    import zipfile

    from build_offline_p2b import build_offline_p2b, zip_offline_pack

    out = build_offline_p2b(REPO_ROOT, tmp_path / "offline_p2b")
    zpath = zip_offline_pack(out, tmp_path / "offline_p2b_OFFLINE_DEMO.zip")
    with zipfile.ZipFile(zpath) as zf:
        names = set(zf.namelist())
    for required in (
        "offline_p2b/index.html",
        "offline_p2b/role_intelligence.html",
        "offline_p2b/role_intelligence.js",
        "offline_p2b/data.js",
        "offline_p2b/app.js",
        "offline_p2b/styles.css",
        "offline_p2b/vendor/bpmn-modeler.production.min.js",
    ):
        assert required in names, required


def test_assets_chrome_citi_personal_trading():
    assets = REPO_ROOT / "notebooks" / "offline_p2b_assets"
    app = (assets / "app.js").read_text(encoding="utf-8")
    styles = (assets / "styles.css").read_text(encoding="utf-8")
    role_js = (assets / "role_intelligence.js").read_text(encoding="utf-8")
    role_html = (assets / "role_intelligence.html").read_text(encoding="utf-8")
    index_html = (assets / "index.html").read_text(encoding="utf-8")

    chrome = "\n".join([app, styles, role_js, role_html, index_html])
    assert "Personal Trading Policy" in chrome
    assert "Policy Follower" in chrome
    assert 'var SHOW_REVIEW_ACCESS = false' in app
    assert 'return "main_view"' in app
    assert "All roles (main view)" in app
    assert "BlackRock" not in chrome
    assert "MCO" not in chrome


def test_pack_offline_demo_bat_zip_only(tmp_path: Path):
    """Python --zip-only path used by pack_offline_demo.bat when pack already exists."""
    import subprocess
    import zipfile

    from build_offline_p2b import build_offline_p2b

    pack = REPO_ROOT / "notebooks" / "offline_p2b"
    if not (pack / "index.html").is_file():
        build_offline_p2b(REPO_ROOT, pack)

    zpath = tmp_path / "offline_p2b_OFFLINE_DEMO.zip"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "notebooks" / "build_offline_p2b.py"),
            "--zip-only",
            "--zip-path",
            str(zpath),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert zpath.is_file()
    with zipfile.ZipFile(zpath) as zf:
        names = set(zf.namelist())
    assert "offline_p2b/index.html" in names
    assert "offline_p2b/role_intelligence.html" in names


def test_cli_build_embeds_latest_role_relevance(tmp_path: Path):
    import subprocess

    from build_offline_p2b import _latest_canonical_run_dir

    canonical = _latest_canonical_run_dir(REPO_ROOT)
    if canonical is None:
        pytest.skip("no policy_runs canonical role_relevance.json present")

    out = tmp_path / "offline_p2b"
    # Point CLI at a temp out by temporarily... build via API using same discovery.
    # Full CLI writes to notebooks/offline_p2b; exercise discovery + embed instead.
    from build_offline_p2b import build_offline_p2b

    built = build_offline_p2b(
        REPO_ROOT,
        out,
        canonical_run_dir=canonical,
        role_relevance_path=canonical / "role_relevance.json",
        policy_knowledge_path=(
            canonical / "policy_knowledge.json"
            if (canonical / "policy_knowledge.json").is_file()
            else None
        ),
    )
    data = (built / "data.js").read_text(encoding="utf-8")
    assert "role_relevance" in data

    # CLI rebuild path (same as bat) must also embed.
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "notebooks" / "build_offline_p2b.py")],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "embedding_role_relevance" in result.stdout
    pack_data = (REPO_ROOT / "notebooks" / "offline_p2b" / "data.js").read_text(
        encoding="utf-8"
    )
    assert "role_relevance" in pack_data
