"""Build a file://-openable policies2BPMN-style offline viewer pack.

Reads ``policies2BPMN/outputs`` and bpmn-js UMD assets as reference only.
Does not modify the ``policies2BPMN`` folder.

Optionally embeds precomputed Pass F ``role_relevance`` + a compact entity
catalog into ``window.P2B_DATA`` for offline intelligence lenses. When those
inputs are omitted or invalid, the pack behaves exactly as before.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ASSETS_DIRNAME = "offline_p2b_assets"
REQUIRED_ASSET_FILES = (
    "index.html",
    "app.js",
    "styles.css",
    "role_intelligence.html",
    "role_intelligence.js",
)

_CATALOG_COLLECTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("requirements", "requirement", ("text", "id")),
    ("roles", "role", ("name", "description", "id")),
    ("actions", "action", ("label", "description", "id")),
    ("decisions", "decision", ("question", "id")),
    ("risks", "risk", ("name", "description", "id")),
    ("controls", "control", ("name", "description", "id")),
    ("evidence", "evidence", ("name", "description", "id")),
    ("findings", "finding", ("description", "id")),
)


def build_canonical_catalog(policy_knowledge: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Compact id → {type, label, source_refs} map for offline lens labels."""
    catalog: dict[str, dict[str, Any]] = {}
    for collection, artifact_type, label_keys in _CATALOG_COLLECTIONS:
        for item in policy_knowledge.get(collection) or []:
            if not isinstance(item, dict):
                continue
            artifact_id = item.get("id")
            if not artifact_id:
                continue
            label = ""
            for key in label_keys:
                value = item.get(key)
                if value:
                    label = str(value)
                    break
            catalog[str(artifact_id)] = {
                "type": artifact_type,
                "label": label or str(artifact_id),
                "source_refs": list(item.get("source_refs") or []),
            }
    for block in policy_knowledge.get("source_blocks") or []:
        if not isinstance(block, dict):
            continue
        block_id = block.get("id")
        if not block_id:
            continue
        excerpt = str(block.get("text") or "")[:240]
        catalog[str(block_id)] = {
            "type": "source",
            "label": excerpt or str(block_id),
            "source_refs": [str(block_id)],
            "locator": block.get("source_locator") or "",
            "section": block.get("section_path") or "",
        }
    return catalog


def load_role_intelligence(
    *,
    role_relevance_path: Path | None = None,
    policy_knowledge_path: Path | None = None,
    canonical_run_dir: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]] | None]:
    """Load optional Pass F artifact + catalog. Returns (None, None) if unavailable."""
    rr_path = Path(role_relevance_path) if role_relevance_path else None
    pk_path = Path(policy_knowledge_path) if policy_knowledge_path else None
    if canonical_run_dir is not None:
        run_dir = Path(canonical_run_dir)
        canonical = run_dir / "outputs" / "canonical"
        if not canonical.is_dir():
            # Allow passing the canonical dir itself.
            canonical = run_dir if run_dir.name == "canonical" else canonical
        if rr_path is None:
            candidate = canonical / "role_relevance.json"
            if candidate.is_file():
                rr_path = candidate
        if pk_path is None:
            candidate = canonical / "policy_knowledge.json"
            if candidate.is_file():
                pk_path = candidate

    role_relevance: dict[str, Any] | None = None
    if rr_path is not None and rr_path.is_file():
        try:
            loaded = json.loads(rr_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, dict) and isinstance(loaded.get("perspectives"), dict):
            role_relevance = loaded

    catalog: dict[str, dict[str, Any]] | None = None
    if pk_path is not None and pk_path.is_file():
        try:
            knowledge = json.loads(pk_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            knowledge = None
        if isinstance(knowledge, dict):
            catalog = build_canonical_catalog(knowledge)

    if role_relevance is None:
        return None, None
    return role_relevance, catalog or {}


# Heuristic role → workflow mapping for offline packs (LLM map may replace later).
_ROLE_WORKFLOW_HEURISTIC: dict[str, list[tuple[str, str, str]]] = {
    "business_owner": [
        ("PTP-PRECLEAR", "PRIMARY", "Get approval before you trade."),
        ("PTP-CERT", "PRIMARY", "Complete yearly training and attest."),
        ("PTP-EXCEPTION", "PRIMARY", "Ask before any exception to the policy."),
        ("PTP-DISC", "SECONDARY", "Disclose reportable accounts."),
        ("PTP-BROKER", "SECONDARY", "Keep accounts with approved brokers."),
        ("PTP-SHORT", "SECONDARY", "Avoid short-term trading profits."),
        ("PTP-PRIVATE", "SECONDARY", "Get pre-approval for private investments."),
        ("PTP-TXTYPE", "SECONDARY", "Apply the right pre-clearance rules by transaction type."),
    ],
    "compliance_officer": [
        ("PTP-VIOL", "PRIMARY", "Review and address personal trading violations."),
        ("PTP-INSIDER", "PRIMARY", "Monitor and prevent insider trading."),
        ("PTP-BLACKOUT", "PRIMARY", "Enforce blackout period restrictions."),
        ("PTP-PROHIB", "PRIMARY", "Test prohibited investment rules."),
        ("PTP-PRECLEAR", "PRIMARY", "Verify pre-clearance happened before trades."),
        ("PTP-CERT", "SECONDARY", "Confirm annual certifications completed."),
        ("PTP-MANAGED", "SECONDARY", "Review exempt managed-account handling."),
    ],
    "policy_owner": [
        ("PTP-POLICY", "PRIMARY", "Own the end-to-end personal trading policy process."),
        ("PTP-VIOL", "PRIMARY", "Ensure violation handling is covered by the policy."),
        ("PTP-EXCEPTION", "PRIMARY", "Ensure exception approval is governed."),
        ("PTP-INSIDER", "SECONDARY", "Insider trading controls must stay covered."),
        ("PTP-SEC-1", "SECONDARY", "Introduction / obligations framing for the policy."),
        ("PTP-PROHIB", "SECONDARY", "Prohibited investment rules are policy coverage."),
    ],
}


def build_role_workflow_map(
    index: list[dict[str, Any]],
    *,
    llm_map: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Build role→workflow map. Prefer validated LLM map; else heuristic filtered by index."""
    known = {str(item.get("workflow_id") or "") for item in index if item.get("workflow_id")}
    known.discard("")

    def _from_entries(entries: list[tuple[str, str, str]]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for workflow_id, relevance, why in entries:
            if workflow_id not in known:
                continue
            out.append(
                {
                    "workflow_id": workflow_id,
                    "relevance": relevance,
                    "why": why,
                }
            )
        return out

    if isinstance(llm_map, dict) and llm_map:
        result: dict[str, list[dict[str, str]]] = {}
        for role in ("business_owner", "compliance_officer", "policy_owner"):
            raw = llm_map.get(role) or []
            cleaned: list[dict[str, str]] = []
            if isinstance(raw, list):
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    wid = str(item.get("workflow_id") or "")
                    if wid not in known:
                        continue
                    cleaned.append(
                        {
                            "workflow_id": wid,
                            "relevance": str(item.get("relevance") or "SECONDARY"),
                            "why": str(item.get("why") or ""),
                        }
                    )
            result[role] = cleaned or _from_entries(_ROLE_WORKFLOW_HEURISTIC.get(role) or [])
        return result

    return {
        role: _from_entries(entries)
        for role, entries in _ROLE_WORKFLOW_HEURISTIC.items()
    }


def _vendored_bpmn_dir(repo_root: Path) -> Path | None:
    """Flat vendor dir (modeler + css + bpmn-font) shipped under assets or pack."""
    for rel in (
        ("notebooks", ASSETS_DIRNAME, "vendor"),
        ("notebooks", "offline_p2b", "vendor"),
    ):
        cand = repo_root.joinpath(*rel)
        if (cand / "bpmn-modeler.production.min.js").is_file():
            return cand
    return None


def _modeler_umd(repo_root: Path) -> Path:
    nm = (
        repo_root
        / "policies2BPMN"
        / "viewer"
        / "node_modules"
        / "bpmn-js"
        / "dist"
        / "bpmn-modeler.production.min.js"
    )
    if nm.is_file():
        return nm
    vendored = _vendored_bpmn_dir(repo_root)
    if vendored is not None:
        return vendored / "bpmn-modeler.production.min.js"
    return nm


def _bpmn_assets_dir(repo_root: Path) -> Path:
    nm = (
        repo_root
        / "policies2BPMN"
        / "viewer"
        / "node_modules"
        / "bpmn-js"
        / "dist"
        / "assets"
    )
    if nm.is_dir():
        return nm
    vendored = _vendored_bpmn_dir(repo_root)
    if vendored is not None:
        return vendored
    return nm


def _require_file(path: Path, hint: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"{hint}: missing {path}")
    return path


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        _rmtree(dest)
    shutil.copytree(src, dest)


def _rmtree(path: Path) -> None:
    """Remove a directory tree; tolerate Windows file locks where possible."""
    import sys

    def _on_rm_error(func, p, exc):  # noqa: ANN001
        import os
        import stat
        import time

        # onerror (≤3.11) passes exc_info; onexc (3.12+) passes the exception.
        cause = exc[1] if isinstance(exc, tuple) else exc
        try:
            os.chmod(p, stat.S_IWRITE)
            time.sleep(0.05)
            func(p)
        except Exception as retry_exc:  # noqa: BLE001
            raise retry_exc from cause

    # onexc is Python 3.12+; onerror remains the 3.11-compatible API.
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_on_rm_error)
    else:
        shutil.rmtree(path, onerror=_on_rm_error)


def build_offline_p2b(
    repo_root: Path,
    out_dir: Path,
    *,
    role_relevance_path: Path | None = None,
    policy_knowledge_path: Path | None = None,
    canonical_run_dir: Path | None = None,
) -> Path:
    """Package an offline HTML viewer into ``out_dir`` and return that path.

    Optional role-intelligence kwargs embed Pass F output into ``P2B_DATA``.
    Missing or invalid inputs are skipped (legacy pack unchanged).
    """
    repo_root = Path(repo_root).resolve()
    out_dir = Path(out_dir).resolve()

    outputs = repo_root / "policies2BPMN" / "outputs"
    index_path = _require_file(outputs / "index.json", "policies2BPMN outputs index")
    assets_src = repo_root / "notebooks" / ASSETS_DIRNAME
    for name in REQUIRED_ASSET_FILES:
        _require_file(assets_src / name, "offline pack template")

    modeler = _modeler_umd(repo_root)
    if not modeler.is_file():
        raise FileNotFoundError(
            "bpmn-modeler UMD not found. Prefer notebooks/offline_p2b_assets/vendor/ "
            "(seeded for CITI lean packs) or run npm install under policies2BPMN/viewer. "
            f"Looked at: {modeler}"
        )
    bpmn_assets = _bpmn_assets_dir(repo_root)
    if not bpmn_assets.is_dir():
        raise FileNotFoundError(f"bpmn-js assets directory missing: {bpmn_assets}")

    index: list[dict[str, Any]] = json.loads(index_path.read_text(encoding="utf-8"))
    workflows: dict[str, dict[str, Any]] = {}
    for item in index:
        wid = item["workflow_id"]
        json_name = item.get("json") or f"{wid}.json"
        bpmn_name = item.get("bpmn") or f"{wid}.bpmn"
        json_path = _require_file(outputs / json_name, f"workflow JSON for {wid}")
        bpmn_path = _require_file(outputs / bpmn_name, f"workflow BPMN for {wid}")
        workflows[wid] = {
            "json": json.loads(json_path.read_text(encoding="utf-8")),
            "bpmn": bpmn_path.read_text(encoding="utf-8"),
        }

    policy_source_path = outputs / "policy_source.html"
    policy_source_html = (
        policy_source_path.read_text(encoding="utf-8")
        if policy_source_path.is_file()
        else "<!DOCTYPE html><html><body><p>No policy_source.html in outputs.</p></body></html>"
    )

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "index": index,
        "workflows": workflows,
        "policy_source_html": policy_source_html,
    }

    role_relevance, catalog = load_role_intelligence(
        role_relevance_path=role_relevance_path,
        policy_knowledge_path=policy_knowledge_path,
        canonical_run_dir=canonical_run_dir,
    )
    if role_relevance is not None:
        payload["role_relevance"] = role_relevance
        payload["canonical_catalog"] = catalog or {}

    llm_map = None
    if isinstance(role_relevance, dict):
        llm_map = role_relevance.get("role_workflow_map")
    payload["role_workflow_map"] = build_role_workflow_map(index, llm_map=llm_map)

    if out_dir.exists():
        try:
            _rmtree(out_dir)
        except OSError:
            # Fall back to overwrite-in-place when a browser/server holds a lock.
            pass
    out_dir.mkdir(parents=True, exist_ok=True)
    vendor = out_dir / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)

    for name in REQUIRED_ASSET_FILES:
        shutil.copy2(assets_src / name, out_dir / name)

    shutil.copy2(modeler, vendor / "bpmn-modeler.production.min.js")
    shutil.copy2(bpmn_assets / "bpmn-js.css", vendor / "bpmn-js.css")
    shutil.copy2(bpmn_assets / "diagram-js.css", vendor / "diagram-js.css")
    font_src = bpmn_assets / "bpmn-font"
    if font_src.is_dir():
        _copy_tree(font_src, vendor / "bpmn-font")

    data_js = "window.P2B_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    (out_dir / "data.js").write_text(data_js, encoding="utf-8")
    (out_dir / "policy_source.html").write_text(policy_source_html, encoding="utf-8")

    readme = "\n".join(
        [
            "Offline policy process demo (main + role views)",
            "================================================",
            "",
            "Open index.html in a browser (file://). No network required.",
            "",
            "Main view: index.html",
            "  - Intelligence lens → All roles (main view) stays here",
            "  - Policy Follower / Compliance Officer / Policy Owner open role tabs",
            "",
            "Role views: role_intelligence.html?lens=business_owner|compliance_officer|policy_owner",
            "  - Same workflow BPMN as main, filtered per role",
            "",
            "Included: app.js, styles.css, data.js, role_intelligence.*, vendor/, policy_source.html",
            "",
        ]
    )
    (out_dir / "README_OFFLINE.txt").write_text(readme, encoding="utf-8")

    manifest = {
        "kind": "offline_p2b",
        "generated_at": payload["generated_at"],
        "workflow_count": len(index),
        "source_outputs": str(outputs),
        "role_relevance_embedded": role_relevance is not None,
        "role_workflow_map_embedded": True,
        "role_views": [
            "role_intelligence.html?lens=business_owner",
            "role_intelligence.html?lens=compliance_officer",
            "role_intelligence.html?lens=policy_owner",
        ],
        "note": "Open index.html via file://. Role lenses open role_intelligence.html. No network required.",
    }
    (out_dir / "OFFLINE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return out_dir


_OFFLINE_ZIP_NAMES = (
    "index.html",
    "app.js",
    "styles.css",
    "data.js",
    "role_intelligence.html",
    "role_intelligence.js",
    "policy_source.html",
    "OFFLINE_MANIFEST.json",
    "README_OFFLINE.txt",
)


def zip_offline_pack(
    pack_dir: Path,
    zip_path: Path | None = None,
) -> Path:
    """Zip the offline pack (main + role views + vendor) for workstation demo handoff."""
    import zipfile

    pack_dir = Path(pack_dir).resolve()
    if not (pack_dir / "index.html").is_file():
        raise FileNotFoundError(f"offline pack missing index.html: {pack_dir}")

    if zip_path is None:
        zip_path = pack_dir.parent / "offline_p2b_OFFLINE_DEMO.zip"
    else:
        zip_path = Path(zip_path)
        if not zip_path.is_absolute():
            # CLI relative paths are cwd-based (e.g. notebooks/offline_p2b_OFFLINE_DEMO.zip).
            zip_path = (Path.cwd() / zip_path).resolve()
        else:
            zip_path = zip_path.resolve()
        if zip_path.is_dir():
            zip_path = zip_path / "offline_p2b_OFFLINE_DEMO.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists() and zip_path.is_file():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in _OFFLINE_ZIP_NAMES:
            src = pack_dir / name
            if src.is_file():
                zf.write(src, arcname=f"offline_p2b/{name}")
        vendor = pack_dir / "vendor"
        if vendor.is_dir():
            for path in vendor.rglob("*"):
                if path.is_file():
                    zf.write(path, arcname=f"offline_p2b/{path.relative_to(pack_dir).as_posix()}")
    return zip_path


def _latest_canonical_run_dir(repo_root: Path) -> Path | None:
    """Newest notebooks/policy_runs/*/…/outputs/canonical with role_relevance.json."""
    runs_root = Path(repo_root) / "notebooks" / "policy_runs"
    if not runs_root.is_dir():
        return None
    candidates: list[Path] = []
    for canonical in runs_root.glob("*/*/outputs/canonical"):
        if (canonical / "role_relevance.json").is_file():
            candidates.append(canonical)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


if __name__ == "__main__":
    import argparse

    root = Path(__file__).resolve().parents[1]
    target = root / "notebooks" / "offline_p2b"
    parser = argparse.ArgumentParser(description="Build and/or zip offline_p2b demo pack")
    parser.add_argument(
        "--zip-only",
        action="store_true",
        help="Only zip an existing notebooks/offline_p2b pack (no rebuild)",
    )
    parser.add_argument(
        "--zip-path",
        type=Path,
        default=None,
        help="Output zip path (default: notebooks/offline_p2b_OFFLINE_DEMO.zip)",
    )
    args = parser.parse_args()

    if not args.zip_only:
        canonical = _latest_canonical_run_dir(root)
        build_kwargs: dict[str, Path] = {}
        if canonical is not None:
            build_kwargs["canonical_run_dir"] = canonical
            build_kwargs["role_relevance_path"] = canonical / "role_relevance.json"
            pk = canonical / "policy_knowledge.json"
            if pk.is_file():
                build_kwargs["policy_knowledge_path"] = pk
            print("embedding_role_relevance", canonical)
        built = build_offline_p2b(root, target, **build_kwargs)
        print(built / "index.html")
        print((built / "index.html").as_uri())
    else:
        built = target

    zipped = zip_offline_pack(built, args.zip_path)
    print("offline_demo_zip", zipped)
