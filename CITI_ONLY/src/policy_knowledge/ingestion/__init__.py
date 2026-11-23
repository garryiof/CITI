"""Document ingestion and provenance."""

from __future__ import annotations

from pathlib import Path

from policy_knowledge.model.schemas import SourceBlock

from .docx_reader import read_docx
from .html_reader import read_html
from .pdf_reader import read_pdf


def read_policy(path: Path, *, policy_id: str = "POLICY_001") -> list[SourceBlock]:
    """Dispatch by suffix to the appropriate reader."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Policy file not found: {path}")
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return read_html(path, policy_id=policy_id)
    if suffix == ".docx":
        return read_docx(path, policy_id=policy_id)
    if suffix == ".pdf":
        return read_pdf(path, policy_id=policy_id)
    raise ValueError(f"Unsupported policy file type: {suffix}")


__all__ = ["read_policy", "read_html", "read_docx", "read_pdf"]
