"""OKF tree validation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from policy_knowledge.validation.schema_validator import ValidationReport

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def validate_okf(okf_dir: Path) -> ValidationReport:
    okf_dir = Path(okf_dir)
    errors: list[str] = []
    warnings: list[str] = []
    manifest_path = okf_dir / "manifest.json"
    if not manifest_path.exists():
        return ValidationReport(ok=False, errors=["manifest.json missing"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "okf-0.2":
        errors.append("schema_version must be okf-0.2")
    for required in ("README.md", "index.md", "policy.md", "sources/source_index.json"):
        if not (okf_dir / required).exists():
            errors.append(f"missing {required}")

    entity_ids: set[str] = set()
    for md in okf_dir.rglob("*.md"):
        if md.name in {"README.md", "index.md"}:
            continue
        text = md.read_text(encoding="utf-8")
        m = FRONTMATTER_RE.match(text)
        if not m:
            errors.append(f"missing frontmatter: {md.relative_to(okf_dir)}")
            continue
        meta = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        for key in ("id", "type", "title", "policy_id", "review_status", "generated_at"):
            if key not in meta:
                errors.append(f"{md.name} missing frontmatter field {key}")
        if "id" in meta:
            entity_ids.add(meta["id"].strip())

    edges_path = okf_dir / "relationships" / "edges.json"
    if edges_path.exists():
        edges = json.loads(edges_path.read_text(encoding="utf-8"))
        for edge in edges:
            for end in ("source_id", "target_id"):
                node = edge.get(end)
                if node and node not in entity_ids and not str(node).startswith("SRC-"):
                    warnings.append(f"edge {end} {node} not in markdown entity set")
    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)
