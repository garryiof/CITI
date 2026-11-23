"""SHA256 checksum helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_checksums(paths: list[Path], output: Path) -> Path:
    lines = []
    for path in paths:
        if path and Path(path).exists():
            digest = sha256_file(path)
            lines.append(f"{digest}  {Path(path).name}")
    output = Path(output)
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return output
