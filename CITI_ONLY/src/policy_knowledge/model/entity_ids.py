"""Deterministic stable identifiers — no random UUIDs as sole IDs."""

from __future__ import annotations

import hashlib
import re


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _digest(*parts: str, length: int = 16) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:length]


def stable_source_id(
    *,
    document_hash: str,
    locator: str,
    text: str,
    sequence: int,
) -> str:
    """SRC-NNNN style id derived from ordered content checksum + locator."""
    payload = _digest(document_hash, locator, _norm(text), str(sequence), length=8)
    # Map hex digest to a stable 4-digit-ish numeric suffix while staying hex-stable.
    numeric = int(payload[:8], 16) % 10000
    return f"SRC-{numeric:04d}"


def stable_entity_id(entity_type: str, normalized_key: str, primary_source_id: str) -> str:
    digest = _digest(entity_type.lower(), _norm(normalized_key), primary_source_id)
    prefix = {
        "requirement": "REQ",
        "role": "ROLE",
        "action": "ACT",
        "process": "PROC",
        "decision": "DEC",
        "risk": "RISK",
        "control": "CTL",
        "evidence": "EVID",
        "section": "SEC",
    }.get(entity_type.lower(), "ENT")
    return f"{prefix}-{digest[:12].upper()}"


def stable_edge_id(
    source_id: str,
    relation_type: str,
    target_id: str,
    provenance_key: str,
) -> str:
    digest = _digest(source_id, relation_type, target_id, provenance_key)
    return f"EDGE-{digest[:12].upper()}"
