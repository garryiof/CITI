"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
NOTEBOOKS = ROOT / "notebooks"
for _path in (SRC, NOTEBOOKS):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_configure(config):  # noqa: ARG001
    """Ensure src and notebooks are importable from the repo root."""
    for path in (SRC, NOTEBOOKS):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
