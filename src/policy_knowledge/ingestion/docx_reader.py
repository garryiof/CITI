"""DOCX policy reader via python-docx."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from policy_knowledge.ingestion.normalizer import RawBlock, document_hash_bytes, to_source_blocks
from policy_knowledge.model.schemas import SourceBlock


def _iter_block_items(parent):
    """Yield paragraphs and tables in document order."""
    from docx.oxml.ns import qn
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P

    parent_elm = parent.element.body
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def read_docx(path: Path, *, policy_id: str = "POLICY_001") -> list[SourceBlock]:
    data = Path(path).read_bytes()
    doc = Document(str(path))
    raw: list[RawBlock] = []
    section_parts: list[str] = []
    para_idx = 0
    table_idx = 0

    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            para_idx += 1
            text = (block.text or "").strip()
            if not text:
                continue
            style_name = (block.style.name if block.style is not None else "") or ""
            if style_name.startswith("Heading"):
                try:
                    level = int(style_name.replace("Heading", "").strip() or "1")
                except ValueError:
                    level = 1
                section_parts[:] = section_parts[: level - 1] + [text]
                raw.append(
                    RawBlock(
                        section_path=" / ".join(section_parts) or text,
                        text=text,
                        block_type="heading",
                        source_locator=f"docx:paragraph[{para_idx}]",
                    )
                )
            else:
                raw.append(
                    RawBlock(
                        section_path=" / ".join(section_parts) or "ROOT",
                        text=text,
                        block_type="paragraph",
                        source_locator=f"docx:paragraph[{para_idx}]",
                    )
                )
        elif isinstance(block, Table):
            table_idx += 1
            rows = []
            for row in block.rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                rows.append(" | ".join(cells))
            text = "\n".join(r for r in rows if r.strip())
            if text:
                raw.append(
                    RawBlock(
                        section_path=" / ".join(section_parts) or "ROOT",
                        text=text,
                        block_type="table",
                        source_locator=f"docx:table[{table_idx}]",
                    )
                )

    return to_source_blocks(raw, policy_id=policy_id, document_hash=document_hash_bytes(data))
