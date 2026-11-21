"""Normalize headings/lists/tables into SourceBlock sequences."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from policy_knowledge.model.entity_ids import stable_source_id
from policy_knowledge.model.schemas import SourceBlock


@dataclass
class RawBlock:
    section_path: str
    text: str
    block_type: str
    source_locator: str


def document_hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def document_hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def to_source_blocks(
    raw_blocks: list[RawBlock],
    *,
    policy_id: str,
    document_hash: str,
) -> list[SourceBlock]:
    blocks: list[SourceBlock] = []
    for idx, raw in enumerate(raw_blocks, start=1):
        text = raw.text.strip()
        if not text:
            continue
        block_id = stable_source_id(
            document_hash=document_hash,
            locator=raw.source_locator,
            text=text,
            sequence=idx,
        )
        blocks.append(
            SourceBlock(
                id=block_id,
                policy_id=policy_id,
                section_path=raw.section_path or "ROOT",
                text=text,
                block_type=raw.block_type,
                source_locator=raw.source_locator,
                sequence=idx,
                document_hash=document_hash,
            )
        )
    # Re-sequence after empty skips so sequences are contiguous 1..n
    for i, block in enumerate(blocks, start=1):
        block.sequence = i
        block.id = stable_source_id(
            document_hash=document_hash,
            locator=block.source_locator,
            text=block.text,
            sequence=i,
        )
    return blocks
