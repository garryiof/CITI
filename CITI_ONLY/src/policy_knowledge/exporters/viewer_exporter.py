"""Offline demo builder: data.js + staged demo/ assets."""

from __future__ import annotations

from typing import Optional


import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from policy_knowledge.config import TransferPolicy
from policy_knowledge.exporters.bpmn_exporter import export_bpmn
from policy_knowledge.exporters.matrix_exporter import export_matrices
from policy_knowledge.exporters.okf_exporter import export_okf
from policy_knowledge.model.graph import to_cytoscape_elements
from policy_knowledge.model.schemas import PolicyKnowledge
from policy_knowledge.validation.quality_report import build_quality_report

VIEWER_ROOT = Path(__file__).resolve().parents[1] / "viewer"
VENDOR_DIR = VIEWER_ROOT / "vendor"
REQUIRED_VENDOR = ("bpmn-navigated-viewer.min.js", "cytoscape.min.js")


@dataclass
class VendorReadiness:
    interactive_ready: bool
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def check_vendor_readiness(vendor_dir: Optional[Path] = None) -> VendorReadiness:
    vendor_dir = Path(vendor_dir or VENDOR_DIR)
    missing: list[str] = []
    notes: list[str] = []
    for name in REQUIRED_VENDOR:
        path = vendor_dir / name
        if not path.exists():
            missing.append(name)
            continue
        # Reject tiny stubs mistakenly placed as production names
        if path.stat().st_size < 10_000:
            missing.append(f"{name} (too small; likely stub)")
            notes.append(f"{name} present but below interactive size threshold")
        content = path.read_text(encoding="utf-8", errors="ignore")
        if "NON-PRODUCTION STUB" in content:
            missing.append(f"{name} (stub)")
            notes.append(f"{name} is a non-production stub")
    return VendorReadiness(interactive_ready=not missing, missing=missing, notes=notes)


def _js_string(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _prepare_role_relevance(
    role_relevance: Optional[dict],
    *,
    redacted: bool,
) -> Optional[dict]:
    """Embed role_relevance; redact why_relevant text when excerpts are disabled."""
    if not role_relevance:
        return None
    if not redacted:
        return role_relevance
    payload = json.loads(json.dumps(role_relevance))
    perspectives = payload.get("perspectives") or {}
    for body in perspectives.values():
        for item in body.get("assessments") or []:
            if "why_relevant" in item:
                item["why_relevant"] = "[redacted]"
    return payload


def _redact_cy_elements(elements: list[dict]) -> list[dict]:
    """Replace passage-bearing Cytoscape labels with stable ids."""
    redacted: list[dict] = []
    for el in elements:
        data = dict(el.get("data") or {})
        if "label" in data:
            data["label"] = data.get("id", "[redacted]")
        redacted.append({**el, "data": data})
    return redacted


def build_offline_demo(
    knowledge: PolicyKnowledge,
    run_dir: Path,
    *,
    transfer_policy: Optional[TransferPolicy] = None,
    role_relevance: Optional[dict] = None,
) -> Path:
    run_dir = Path(run_dir)
    transfer_policy = transfer_policy or TransferPolicy()
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)

    # Ensure derived artifacts exist for packaging into data.js
    okf_dir = outputs / "okf"
    if not (okf_dir / "manifest.json").exists():
        export_okf(knowledge, okf_dir)
    bpmn_dir = outputs / "bpmn"
    if not any(bpmn_dir.glob("*")):
        export_bpmn(knowledge, bpmn_dir)
    matrices_dir = outputs / "matrices"
    if not (matrices_dir / "role_matrix.csv").exists():
        export_matrices(knowledge, matrices_dir)

    viewer_out = outputs / "viewer"
    demo = run_dir / "demo"
    demo.mkdir(parents=True, exist_ok=True)
    vendor_demo = demo / "vendor"
    vendor_demo.mkdir(parents=True, exist_ok=True)

    readiness = check_vendor_readiness(VENDOR_DIR)
    # Copy real vendors if present; else copy stubs for structure only.
    for name in REQUIRED_VENDOR:
        src = VENDOR_DIR / name
        stub = VENDOR_DIR / "stubs" / name
        if src.exists() and "NON-PRODUCTION STUB" not in src.read_text(encoding="utf-8", errors="ignore") and src.stat().st_size >= 10_000:
            shutil.copy2(src, vendor_demo / name)
        elif stub.exists():
            shutil.copy2(stub, vendor_demo / name)
        else:
            (vendor_demo / name).write_text(
                "/* missing vendor asset */\n",
                encoding="utf-8",
            )

    shutil.copy2(VIEWER_ROOT / "template.html", demo / "index.html")
    shutil.copy2(VIEWER_ROOT / "app.js", demo / "app.js")
    shutil.copy2(VIEWER_ROOT / "styles.css", demo / "styles.css")

    # data.js feeds demo/index.html (via window.POLICY_DEMO_DATA).
    # Default: always populate full parsed content so the HTML shows requirements,
    # sources, and BPMN. Set include_policy_excerpts_in_demo=False only when you
    # intentionally need a redacted demo package.
    redacted = not transfer_policy.include_policy_excerpts_in_demo
    bpmn_xml = ""
    no_process = None
    bpmn_file = bpmn_dir / "policy_process.bpmn"
    no_file = bpmn_dir / "no_supported_process.json"
    if bpmn_file.exists():
        bpmn_xml = bpmn_file.read_text(encoding="utf-8")
    if no_file.exists():
        no_process = json.loads(no_file.read_text(encoding="utf-8"))

    sources = []
    for block in knowledge.source_blocks:
        sources.append(
            {
                "id": block.id,
                "section_path": block.section_path if not redacted else "",
                "locator": block.source_locator if not redacted else "",
                "excerpt": "" if redacted else block.text[:500],
            }
        )

    def _entities(items: list, text_keys: tuple[str, ...]) -> list[dict]:
        rows = []
        for item in items:
            data = item.model_dump()
            if redacted:
                for key in text_keys:
                    if key in data and isinstance(data[key], str):
                        data[key] = "[redacted]"
                if "source_refs" in data:
                    # Keep ids for cross-view sync; omit passage text elsewhere.
                    pass
            rows.append(data)
        return rows

    payload = {
        "policy": {
            **knowledge.policy.model_dump(),
            **(
                {"title": knowledge.policy.title, "input_path": "[redacted]"}
                if redacted
                else {}
            ),
        },
        "mode": "redacted" if redacted else "full_fidelity",
        "mode_note": (
            "Source excerpts and sensitive passages omitted (include_policy_excerpts_in_demo=False)."
            if redacted
            else "Full parsed policy embedded in data.js for the offline HTML demo."
        ),
        "interactive_ready": readiness.interactive_ready,
        "vendor_missing": readiness.missing,
        "browser_test": "BROWSER_TEST_NOT_RUN",
        "requirements": _entities(knowledge.requirements, ("text",)),
        "roles": _entities(knowledge.roles, ("description", "name")),
        "actions": _entities(knowledge.actions, ("description", "label")),
        "risks": _entities(knowledge.risks, ("description", "name")),
        "controls": _entities(knowledge.controls, ("description", "name")),
        "evidence": _entities(knowledge.evidence, ("description", "name")),
        "findings": _entities(knowledge.findings, ("description",)),
        "sources": sources,
        "cy_elements": _redact_cy_elements(to_cytoscape_elements(knowledge))
        if redacted
        else to_cytoscape_elements(knowledge),
        "bpmn_xml": "" if redacted else bpmn_xml,
        "no_process": no_process,
        "okf_index": [r.id for r in knowledge.requirements] if redacted else [
            f"{r.id}: {r.text[:80]}" for r in knowledge.requirements
        ],
        "qa": build_quality_report(knowledge),
        "role_relevance": _prepare_role_relevance(role_relevance, redacted=redacted),
    }

    data_js = "window.POLICY_DEMO_DATA = " + _js_string(payload) + ";\n"
    (demo / "data.js").write_text(data_js, encoding="utf-8")
    (viewer_out).mkdir(parents=True, exist_ok=True)
    (viewer_out / "data.js").write_text(data_js, encoding="utf-8")

    manifest = {
        "mode": payload["mode"],
        "interactive_ready": readiness.interactive_ready,
        "vendor_missing": readiness.missing,
        "browser_test": "BROWSER_TEST_NOT_RUN",
        "policy_id": knowledge.policy.id,
        "include_policy_excerpts": not redacted,
    }
    (demo / "DEMO_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return demo
