"""ZIP safety checks."""

from __future__ import annotations

import zipfile
from pathlib import Path


def is_zip_slip(member: str) -> bool:
    norm = member.replace("\\", "/")
    if norm.startswith("/") or norm.startswith("../") or "/../" in f"/{norm}/":
        return True
    return False


def validate_zip(path: Path) -> list[str]:
    errors: list[str] = []
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            errors.append(f"corrupt member: {bad}")
        for info in zf.infolist():
            name = info.filename
            if is_zip_slip(name):
                errors.append(f"zip-slip path: {name}")
            # Reject symlink-like external attributes on Unix bit if present
            if info.external_attr and (info.external_attr >> 16) & 0o120000 == 0o120000:
                errors.append(f"symlink entry rejected: {name}")
    return errors
