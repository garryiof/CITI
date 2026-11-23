"""PDF policy reader — pypdf primary; optional fallbacks; OCR warning for empty text."""

from __future__ import annotations

import re
import warnings
from pathlib import Path

from policy_knowledge.ingestion.normalizer import RawBlock, document_hash_bytes, to_source_blocks
from policy_knowledge.model.schemas import SourceBlock


class OCRRequiredWarning(UserWarning):
    """Emitted when a PDF yields no extractable text (likely scanned/image-only)."""


def _extract_with_pypdf(path: Path) -> list[tuple[int, str]]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        from PyPDF2 import PdfReader  # type: ignore

    reader = PdfReader(str(path))
    pages: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append((i, text))
    return pages


def _extract_with_pdfminer(path: Path) -> list[tuple[int, str]]:
    from pdfminer.high_level import extract_text  # type: ignore

    text = extract_text(str(path)) or ""
    # pdfminer may not split pages easily here — treat as single locator page 1 chunks.
    return [(1, text)]


def _extract_simple_streams(path: Path) -> list[tuple[int, str]]:
    """Dev fallback for minimal synthetic PDFs when Hub PDF libs are absent."""
    data = path.read_bytes()
    # Very small heuristic: collect Tj string operands.
    texts = re.findall(rb"\((?:\\.|[^\\)])*\)\s*Tj", data)
    decoded: list[str] = []
    for token in texts:
        inner = token[1 : token.rfind(b")")]
        inner = inner.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
        decoded.append(inner.decode("latin-1", errors="replace"))
    joined = " ".join(decoded).strip()
    return [(1, joined)]


def _extract_pages(path: Path) -> list[tuple[int, str]]:
    errors: list[str] = []
    for extractor in (_extract_with_pypdf, _extract_with_pdfminer):
        try:
            return extractor(path)
        except Exception as exc:  # noqa: BLE001 — try next backend
            errors.append(f"{extractor.__name__}: {exc}")
    try:
        return _extract_simple_streams(path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"simple: {exc}")
    raise RuntimeError(
        "No usable PDF text extractor available (pypdf/PyPDF2/pdfminer). "
        + "; ".join(errors)
    )


def read_pdf(path: Path, *, policy_id: str = "POLICY_001") -> list[SourceBlock]:
    path = Path(path)
    data = path.read_bytes()
    pages = _extract_pages(path)
    raw: list[RawBlock] = []
    any_text = False
    for page_no, text in pages:
        cleaned = (text or "").strip()
        if cleaned:
            any_text = True
            raw.append(
                RawBlock(
                    section_path=f"PDF page {page_no}",
                    text=cleaned,
                    block_type="page",
                    source_locator=f"pdf:page[{page_no}]",
                )
            )
    if not any_text:
        warnings.warn(
            f"OCR required: no extractable text in PDF {path.name}. "
            "Do not invent text; enable approved local OCR only if allowed.",
            OCRRequiredWarning,
            stacklevel=2,
        )
        return []
    return to_source_blocks(raw, policy_id=policy_id, document_hash=document_hash_bytes(data))
