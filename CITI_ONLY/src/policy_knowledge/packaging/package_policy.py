"""Create FULL/DEMO archives with transfer gates."""

from __future__ import annotations

from typing import Optional


import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from policy_knowledge.config import TransferPolicy
from policy_knowledge.packaging.archive_validator import validate_zip
from policy_knowledge.packaging.checksums import write_checksums
from policy_knowledge.packaging.content_review import decide_inclusions, inventory_run


@dataclass
class ArchiveResult:
    full_zip: Optional[Path]
    demo_zip: Optional[Path]
    checksums_path: Optional[Path]
    report_path: Path
    passed: bool


def _zip_timestamp() -> str:
    # yyyy-mm-dd-hh:mm:ss — ':' is illegal on Windows, so use '-' for time parts.
    return datetime.now().strftime("%Y-%m-%d-%H-%M-%S")


def _add_tree(zf: zipfile.ZipFile, root: Path, base: Path, prefix: str = "") -> None:
    for file in root.rglob("*"):
        if not file.is_file():
            continue
        rel = file.relative_to(base).as_posix()
        arcname = f"{prefix}{rel}" if prefix else rel
        if arcname.startswith("archive/") or "/archive/" in arcname:
            continue
        zf.write(file, arcname)


def archive_policy_run(run_dir: Path, transfer_policy: TransferPolicy) -> ArchiveResult:
    run_dir = Path(run_dir)
    archive_dir = run_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    inventory = inventory_run(run_dir)
    decisions = decide_inclusions(transfer_policy, inventory)

    policy_id = run_dir.parent.name
    run_id = run_dir.name
    stamp = _zip_timestamp()
    # FULL run ZIP disabled — offline handoff is notebooks/offline_p2b_OFFLINE_DEMO.zip
    full_zip: Optional[Path] = None
    demo_zip_path: Optional[Path] = archive_dir / f"{policy_id}_{stamp}_DEMO.zip"

    include_set = {row["path"] for row in decisions["full_include"]}

    demo_zip: Optional[Path] = None
    demo_blocked_reason = None
    if decisions["demo_allowed"]:
        demo_root = run_dir / "demo"
        with zipfile.ZipFile(demo_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if demo_root.exists():
                for file in demo_root.rglob("*"):
                    if file.is_file():
                        rel = file.relative_to(demo_root).as_posix()
                        zf.write(file, f"demo/{rel}")
        demo_zip = demo_zip_path
    else:
        demo_blocked_reason = decisions["demo_note"]
        demo_zip_path = None

    zips = [p for p in [demo_zip] if p]
    checksums_path = write_checksums(zips, archive_dir / "SHA256SUMS") if zips else None

    errors = []
    for zpath in zips:
        errors.extend(validate_zip(zpath))

    report = {
        "policy_id": policy_id,
        "run_id": run_id,
        "transfer_policy": {
            "workstation_transfer_approved": transfer_policy.workstation_transfer_approved,
            "include_source_in_full": transfer_policy.include_source_in_full,
            "include_intermediate_in_full": transfer_policy.include_intermediate_in_full,
            "include_policy_excerpts_in_demo": transfer_policy.include_policy_excerpts_in_demo,
        },
        "inventory_count": len(inventory),
        "full_include_count": len(include_set),
        "full_omit": decisions["full_omit"],
        "full_zip": None,
        "full_zip_skipped": "disabled; use notebooks/offline_p2b_OFFLINE_DEMO.zip for offline demo",
        "demo_zip": str(demo_zip) if demo_zip else None,
        "demo_blocked_reason": demo_blocked_reason,
        "validation_errors": errors,
        "passed": not errors,
    }
    report_path = archive_dir / "ARCHIVE_REPORT.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return ArchiveResult(
        full_zip=None,
        demo_zip=demo_zip,
        checksums_path=checksums_path,
        report_path=report_path,
        passed=bool(report["passed"]),
    )
