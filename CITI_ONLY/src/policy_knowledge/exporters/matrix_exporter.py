"""CSV matrix exporters."""

from __future__ import annotations

import csv
from pathlib import Path

from policy_knowledge.governance.risk_control_matrix import build_risk_control_rows
from policy_knowledge.governance.role_matrix import build_role_matrix_rows
from policy_knowledge.governance.traceability import build_traceability_rows
from policy_knowledge.model.schemas import PolicyKnowledge


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def export_matrices(knowledge: PolicyKnowledge, output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "role_matrix.csv", build_role_matrix_rows(knowledge))
    _write_csv(output_dir / "risk_control_matrix.csv", build_risk_control_rows(knowledge))
    _write_csv(output_dir / "traceability.csv", build_traceability_rows(knowledge))
    return output_dir
