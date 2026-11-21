"""Heading-aware chunking with overlap metadata."""

from __future__ import annotations

from dataclasses import dataclass, field

from policy_knowledge.model.schemas import SourceBlock


@dataclass
class Chunk:
    sequence: int
    text: str
    section_path: str
    metadata: dict = field(default_factory=dict)


def chunk_blocks(
    blocks: list[SourceBlock],
    *,
    max_chars: int = 12000,
    overlap: int = 200,
) -> list[Chunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    chunks: list[Chunk] = []
    buf: list[SourceBlock] = []
    buf_len = 0
    seq = 1

    def flush(carry: list[SourceBlock] | None = None) -> None:
        nonlocal seq, buf, buf_len
        if not buf:
            return
        text = "\n\n".join(b.text for b in buf)
        chunks.append(
            Chunk(
                sequence=seq,
                text=text,
                section_path=buf[0].section_path,
                metadata={
                    "source_block_ids": [b.id for b in buf],
                    "char_count": len(text),
                    "overlap_chars": overlap if seq > 1 else 0,
                },
            )
        )
        seq += 1
        if carry:
            buf = carry
            buf_len = sum(len(b.text) for b in buf)
        else:
            buf = []
            buf_len = 0

    for block in blocks:
        addition = len(block.text) + (2 if buf else 0)
        if buf and buf_len + addition > max_chars:
            # Keep overlap by retaining trailing blocks that fit overlap budget.
            carry: list[SourceBlock] = []
            carry_len = 0
            for prev in reversed(buf):
                if carry_len + len(prev.text) > overlap:
                    break
                carry.insert(0, prev)
                carry_len += len(prev.text)
            flush(carry=carry)
        buf.append(block)
        buf_len += addition
    flush()
    return chunks
