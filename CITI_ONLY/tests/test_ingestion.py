"""Ingestion readers, normalizer, chunker, deterministic SRC ids."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from policy_knowledge.ingestion import read_policy
from policy_knowledge.ingestion.chunker import chunk_blocks
from policy_knowledge.ingestion.pdf_reader import OCRRequiredWarning, read_pdf

FIXTURES = Path(__file__).parent / "fixtures"


def _write_minimal_docx(path: Path) -> None:
    doc = Document()
    doc.add_heading("Synthetic Escalation Policy", level=1)
    doc.add_heading("1. Purpose", level=2)
    doc.add_paragraph("Analysts must escalate exceptions within 1 business day.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Control"
    table.cell(0, 1).text = "Owner"
    table.cell(1, 0).text = "Dual review"
    table.cell(1, 1).text = "Approver"
    doc.save(path)


def _write_text_pdf(path: Path) -> None:
    # Minimal PDF with a text stream (no external deps).
    content = b"BT /F1 12 Tf 100 700 Td (Analysts must escalate exceptions.) Tj ET"
    objects = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(content)} >>stream\n".encode()
        + content
        + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    xref_positions = []
    out = bytearray(b"%PDF-1.4\n")
    for obj in objects:
        xref_positions.append(len(out))
        out.extend(obj)
    xref_start = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for pos in xref_positions:
        out.extend(f"{pos:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode()
    )
    path.write_bytes(bytes(out))


def _write_image_only_pdf(path: Path) -> None:
    # Page with empty content stream — no extractable text.
    content = b""
    objects = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(content)} >>stream\n".encode()
        + content
        + b"\nendstream\nendobj\n"
    )
    xref_positions = []
    out = bytearray(b"%PDF-1.4\n")
    for obj in objects:
        xref_positions.append(len(out))
        out.extend(obj)
    xref_start = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for pos in xref_positions:
        out.extend(f"{pos:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode()
    )
    path.write_bytes(bytes(out))


def test_html_headings_and_tables():
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    assert blocks
    assert any(b.block_type == "heading" for b in blocks)
    assert any("must escalate" in b.text.lower() for b in blocks)
    assert any(b.block_type == "table" for b in blocks)
    assert all(b.id.startswith("SRC-") for b in blocks)
    # Deterministic for fixed fixture
    again = read_policy(FIXTURES / "synthetic_policy.html")
    assert [b.id for b in blocks] == [b.id for b in again]
    assert [b.sequence for b in blocks] == list(range(1, len(blocks) + 1))


def test_docx_paragraphs_and_tables(tmp_path: Path):
    path = tmp_path / "synthetic_policy.docx"
    _write_minimal_docx(path)
    blocks = read_policy(path)
    assert any("must escalate" in b.text.lower() for b in blocks)
    assert any(b.block_type == "table" for b in blocks)
    assert all(b.source_locator for b in blocks)


def test_pdf_pages_and_ocr_warning(tmp_path: Path):
    text_pdf = tmp_path / "text.pdf"
    _write_text_pdf(text_pdf)
    image_pdf = tmp_path / "image_only.pdf"
    _write_image_only_pdf(image_pdf)

    try:
        text_blocks = read_policy(text_pdf)
    except RuntimeError as exc:
        if "pypdf" in str(exc).lower() or "pdf" in str(exc).lower():
            pytest.skip(f"PDF library unavailable locally: {exc}")
        raise

    assert text_blocks
    assert any("escalate" in b.text.lower() for b in text_blocks)

    with pytest.warns(OCRRequiredWarning):
        empty = read_pdf(image_pdf, policy_id="POLICY_001")
    assert empty == [] or all(not b.text.strip() for b in empty)


def test_missing_and_unsupported_paths(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        read_policy(tmp_path / "missing.html")
    bad = tmp_path / "policy.txt"
    bad.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError):
        read_policy(bad)


def test_chunker_preserves_sequence():
    blocks = read_policy(FIXTURES / "synthetic_policy.html")
    chunks = chunk_blocks(blocks, max_chars=200, overlap=20)
    assert chunks
    assert [c.sequence for c in chunks] == sorted(c.sequence for c in chunks)
    assert all(c.metadata.get("source_block_ids") for c in chunks)
