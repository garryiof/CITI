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


_NUMBERED_HEADING_RE = re.compile(
    r"^\s*(?:(?:Section|Article|Appendix|Part)\s+[A-Z0-9]+(?:\.[0-9]+)*|"
    r"\d+(?:\.\d+){0,3}[.)]?)\s+[A-Z][A-Za-z0-9 ,/&()'’\-:]{2,90}\s*$"
)
_ALLCAPS_HEADING_RE = re.compile(r"^\s*[A-Z][A-Z0-9 ,/&()'’\-:]{3,70}\s*$")
_KNOWN_SECTION_RE = re.compile(
    r"^\s*(?:Objective|Purpose|Scope|Background|Definitions|Roles and Responsibilities|"
    r"Responsibilities|General Principles|Prohibited Activities|Prohibited Transactions|"
    r"Pre-?Clearance(?:\s+Requirements)?|Reportable Accounts|Approved Brokers|"
    r"Account Disclosure|Disclosures|Blackout Periods?|Short-?Term Trading|"
    r"Holding Periods?|Private Investments?|Outside Business Activities|"
    r"Annual Certification|Certification|Training|Recordkeeping|Exceptions|"
    r"Violations(?:\s+and\s+Sanctions)?|Escalation|Monitoring|Governance)\s*:?\s*$"
)


def _is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 95:
        return False
    # Reject lines that read like full prose sentences or numeric values.
    if stripped.endswith(".") and not re.match(r"^\d+\.\s+[A-Z][A-Za-z0-9\s\-/&()]+$", stripped):
        return False
    if _KNOWN_SECTION_RE.match(stripped):
        return True
    if _NUMBERED_HEADING_RE.match(stripped):
        words = stripped.split()
        # Avoid matching e.g. "10,000 USD maximum" or "30 Calendar Days"
        if words[0].rstrip(".").isdigit() and len(words) >= 2 and words[1].lower() in {
            "day", "days", "business", "calendar", "month", "months", "year", "years", "usd", "percent",
        }:
            return False
        return True
    if _ALLCAPS_HEADING_RE.match(stripped) and any(c.isalpha() for c in stripped) and len(stripped.split()) <= 8:
        return True
    return False


def _split_long_text(text: str, max_chars: int = 1800) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) <= 1:
        # Fall back to single-newline splits when PDF extractor flattens blank lines.
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    if len(paragraphs) <= 1:
        return [text]
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for para in paragraphs:
        add = len(para) + (1 if buf else 0)
        if buf and buf_len + add > max_chars:
            chunks.append("\n".join(buf))
            buf = [para]
            buf_len = len(para)
        else:
            buf.append(para)
            buf_len += add
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def _split_page_blocks(page_no: int, text: str) -> list[RawBlock]:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    lines = normalized.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_lines: list[str] = []

    for line in lines:
        if _is_heading_line(line) and (current_lines or not sections):
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = line.strip()
            current_lines = [line.strip()]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, current_lines))

    # If no headings matched and page is short, keep single page block for backwards compatibility.
    has_headings = any(h for h, _ in sections)
    if not has_headings and len(normalized) <= 1800:
        return [
            RawBlock(
                section_path=f"PDF page {page_no}",
                text=normalized,
                block_type="page",
                source_locator=f"pdf:page[{page_no}]",
            )
        ]

    blocks: list[RawBlock] = []
    part_idx = 0
    for heading, sec_lines in sections:
        sec_text = "\n".join(sec_lines).strip()
        if not sec_text:
            continue
        for sub_text in _split_long_text(sec_text):
            part_idx += 1
            sec_label = f"PDF page {page_no} — {heading}" if heading else f"PDF page {page_no}"
            blocks.append(
                RawBlock(
                    section_path=sec_label,
                    text=sub_text,
                    block_type="section" if heading else "page",
                    source_locator=(
                        f"pdf:page[{page_no}]"
                        if part_idx == 1 and len(sections) == 1 and len(sec_text) <= 1800
                        else f"pdf:page[{page_no}]#s{part_idx}"
                    ),
                )
            )
    return blocks


def read_pdf(path: Path, *, policy_id: str = "POLICY_001") -> list[SourceBlock]:
    path = Path(path)
    data = path.read_bytes()
    pages = _extract_pages(path)
    raw: list[RawBlock] = []
    any_text = False
    for page_no, text in pages:
        page_blocks = _split_page_blocks(page_no, text)
        if page_blocks:
            any_text = True
            raw.extend(page_blocks)
    if not any_text:
        warnings.warn(
            f"OCR required: no extractable text in PDF {path.name}. "
            "Do not invent text; enable approved local OCR only if allowed.",
            OCRRequiredWarning,
            stacklevel=2,
        )
        return []
    return to_source_blocks(raw, policy_id=policy_id, document_hash=document_hash_bytes(data))
