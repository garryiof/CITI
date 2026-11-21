"""Reader protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from policy_knowledge.model.schemas import SourceBlock


class PolicyReader(Protocol):
    def __call__(self, path: Path, *, policy_id: str = "POLICY_001") -> list[SourceBlock]: ...
