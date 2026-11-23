"""OKF v0.2 Markdown + manifest exporter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from policy_knowledge.model.schemas import PolicyKnowledge


def _frontmatter(**fields) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}: {json.dumps(value)}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _write_item(
    path: Path,
    *,
    entity_id: str,
    entity_type: str,
    title: str,
    policy_id: str,
    review_status: str,
    source_refs: list[str],
    links: list[str],
    body: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    content = _frontmatter(
        id=entity_id,
        type=entity_type,
        title=title.replace("\n", " ")[:120],
        policy_id=policy_id,
        review_status=review_status,
        source_refs=source_refs,
        links=links,
        generated_at=generated_at,
    )
    content += f"# {title}\n\n{body.strip()}\n"
    if links:
        content += "\n## Links\n\n" + "\n".join(f"- {link}" for link in links) + "\n"
    path.write_text(content, encoding="utf-8")


def export_okf(knowledge: PolicyKnowledge, output_dir: Path) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    policy_id = knowledge.policy.id

    readme = output_dir / "README.md"
    readme.write_text(
        "# OKF v0.2 export\n\nDerived from canonical PolicyKnowledge. Not an external formal standard.\n",
        encoding="utf-8",
    )
    written.append(readme)

    index_lines = ["# OKF Index\n", f"- Policy: [{policy_id}](policy.md)\n"]
    _write_item(
        output_dir / "policy.md",
        entity_id=policy_id,
        entity_type="policy",
        title=knowledge.policy.title,
        policy_id=policy_id,
        review_status=knowledge.policy.review_status,
        source_refs=[],
        links=[f"requirements/{r.id}.md" for r in knowledge.requirements[:20]],
        body=f"Input: `{knowledge.policy.input_path}`\n\nSource hash: `{knowledge.policy.source_hash}`",
    )
    written.append(output_dir / "policy.md")

    def dump_collection(folder: str, items, entity_type: str, title_attr: str, body_attr: str):
        for item in items:
            title = getattr(item, title_attr)
            body = getattr(item, body_attr, None) or title
            rel = f"{folder}/{item.id}.md"
            path = output_dir / rel
            links = [f"../sources/source_index.json#{ref}" for ref in item.source_refs]
            _write_item(
                path,
                entity_id=item.id,
                entity_type=entity_type,
                title=str(title)[:120],
                policy_id=policy_id,
                review_status=getattr(item, "review_status", "extracted"),
                source_refs=list(item.source_refs),
                links=links,
                body=str(body),
            )
            written.append(path)
            index_lines.append(f"- {entity_type}: [{item.id}]({rel})\n")

    dump_collection("requirements", knowledge.requirements, "requirement", "text", "text")
    dump_collection("roles", knowledge.roles, "role", "name", "description")
    dump_collection("actions", knowledge.actions, "action", "label", "description")
    dump_collection("processes", knowledge.processes, "process", "name", "name")
    dump_collection("risks", knowledge.risks, "risk", "name", "description")
    dump_collection("controls", knowledge.controls, "control", "name", "description")
    dump_collection("evidence", knowledge.evidence, "evidence", "name", "description")

    rel_dir = output_dir / "relationships"
    rel_dir.mkdir(parents=True, exist_ok=True)
    edges_path = rel_dir / "edges.json"
    edges_path.write_text(
        json.dumps([e.model_dump() for e in knowledge.edges], indent=2),
        encoding="utf-8",
    )
    written.append(edges_path)
    rel_index = rel_dir / "index.md"
    rel_index.write_text(
        "# Relationships\n\n" + "\n".join(
            f"- `{e.source_id}` —{e.relation_type}→ `{e.target_id}` ({e.derivation})"
            for e in knowledge.edges
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(rel_index)

    sources_dir = output_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    source_index = sources_dir / "source_index.json"
    source_index.write_text(
        json.dumps(
            {
                b.id: {
                    "section_path": b.section_path,
                    "locator": b.source_locator,
                    "text": b.text,
                }
                for b in knowledge.source_blocks
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    written.append(source_index)

    index_path = output_dir / "index.md"
    index_path.write_text("".join(index_lines), encoding="utf-8")
    written.append(index_path)

    manifest = {
        "schema_version": "okf-0.2",
        "generator": "policy_knowledge.exporters.okf_exporter",
        "policy_id": policy_id,
        "source_hash": knowledge.policy.source_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "requirements": len(knowledge.requirements),
            "roles": len(knowledge.roles),
            "actions": len(knowledge.actions),
            "edges": len(knowledge.edges),
        },
        "artifacts": [str(p.relative_to(output_dir)).replace("\\", "/") for p in written],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    written.append(manifest_path)
    return written
