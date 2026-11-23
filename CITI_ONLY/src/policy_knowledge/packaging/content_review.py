"""Pre-transfer content inventory by class."""

from __future__ import annotations

from pathlib import Path

from policy_knowledge.config import TransferPolicy


def inventory_run(run_dir: Path) -> list[dict]:
    run_dir = Path(run_dir)
    rows: list[dict] = []
    classes = {
        "input": "source",
        "intermediate": "intermediate",
        "outputs": "derived",
        "demo": "demo",
        "config_snapshot": "config",
        "logs": "logs",
        "archive": "archive",
    }
    for top, cls in classes.items():
        path = run_dir / top
        if not path.exists():
            continue
        for file in path.rglob("*"):
            if file.is_file():
                rows.append(
                    {
                        "path": str(file.relative_to(run_dir)).replace("\\", "/"),
                        "class": cls,
                        "bytes": file.stat().st_size,
                    }
                )
    return rows


def decide_inclusions(transfer_policy: TransferPolicy, inventory: list[dict]) -> dict:
    include_full = []
    omit_full = []
    for row in inventory:
        cls = row["class"]
        rel = row["path"]
        if cls == "archive" or rel.startswith("archive/"):
            omit_full.append({**row, "reason": "exclude_archive_dir_from_full_zip"})
            continue
        if cls == "source" and not transfer_policy.include_source_in_full:
            omit_full.append({**row, "reason": "include_source_in_full=false"})
            continue
        if cls == "intermediate" and not transfer_policy.include_intermediate_in_full:
            omit_full.append({**row, "reason": "include_intermediate_in_full=false"})
            continue
        include_full.append(row)

    demo_allowed = transfer_policy.workstation_transfer_approved
    demo_note = (
        "workstation_transfer_approved"
        if demo_allowed
        else "blocked: workstation_transfer_approved=false"
    )
    return {
        "full_include": include_full,
        "full_omit": omit_full,
        "demo_allowed": demo_allowed,
        "demo_note": demo_note,
        "excerpts_in_demo": transfer_policy.include_policy_excerpts_in_demo,
    }
