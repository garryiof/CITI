"""Canonical JSON exports."""

from __future__ import annotations

import json
from pathlib import Path

from policy_knowledge.model.graph import to_cytoscape_elements
from policy_knowledge.model.schemas import PolicyKnowledge


def export_canonical_json(knowledge: PolicyKnowledge, output_dir: Path) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    canonical = output_dir / "policy_knowledge.json"
    canonical.write_text(
        knowledge.model_dump_json(indent=2),
        encoding="utf-8",
    )
    paths.append(canonical)
    graph_path = output_dir / "graph_elements.json"
    graph_path.write_text(
        json.dumps(to_cytoscape_elements(knowledge), indent=2),
        encoding="utf-8",
    )
    paths.append(graph_path)
    prov = output_dir / "provenance_index.json"
    prov.write_text(
        json.dumps(
            {b.id: {"locator": b.source_locator, "section": b.section_path} for b in knowledge.source_blocks},
            indent=2,
        ),
        encoding="utf-8",
    )
    paths.append(prov)
    return paths
