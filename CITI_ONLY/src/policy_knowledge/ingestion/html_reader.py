"""HTML policy reader via BeautifulSoup."""

from __future__ import annotations

from typing import Optional


from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

from policy_knowledge.ingestion.normalizer import RawBlock, document_hash_bytes, to_source_blocks
from policy_knowledge.model.schemas import SourceBlock

SKIP_TAGS = {"script", "style", "nav", "footer", "header", "noscript"}


def _dom_path(el: Tag) -> str:
    parts: list[str] = []
    cur: Optional[Tag] = el
    while cur is not None and getattr(cur, "name", None):
        parent = cur.parent if isinstance(cur.parent, Tag) else None
        if parent:
            same = [c for c in parent.find_all(cur.name, recursive=False) if isinstance(c, Tag)]
            if len(same) > 1:
                idx = same.index(cur) + 1
                parts.append(f"{cur.name}[{idx}]")
            else:
                parts.append(cur.name)
        else:
            parts.append(cur.name)
        cur = parent if isinstance(parent, Tag) else None
    return "html:" + "/".join(reversed(parts))


def read_html(path: Path, *, policy_id: str = "POLICY_001") -> list[SourceBlock]:
    data = Path(path).read_bytes()
    soup = BeautifulSoup(data, "lxml")
    for tag in soup.find_all(SKIP_TAGS):
        tag.decompose()

    raw: list[RawBlock] = []
    section_parts: list[str] = []

    body = soup.body or soup
    for el in body.descendants:
        if not isinstance(el, Tag):
            continue
        name = el.name.lower()
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            text = el.get_text(" ", strip=True)
            section_parts[:] = section_parts[: level - 1] + [text]
            raw.append(
                RawBlock(
                    section_path=" / ".join(section_parts) or text,
                    text=text,
                    block_type="heading",
                    source_locator=_dom_path(el) + (f"#{el.get('id')}" if el.get("id") else ""),
                )
            )
        elif name == "p":
            text = el.get_text(" ", strip=True)
            if text:
                raw.append(
                    RawBlock(
                        section_path=" / ".join(section_parts) or "ROOT",
                        text=text,
                        block_type="paragraph",
                        source_locator=_dom_path(el) + (f"#{el.get('id')}" if el.get("id") else ""),
                    )
                )
        elif name in {"li"}:
            text = el.get_text(" ", strip=True)
            if text:
                raw.append(
                    RawBlock(
                        section_path=" / ".join(section_parts) or "ROOT",
                        text=text,
                        block_type="list_item",
                        source_locator=_dom_path(el) + (f"#{el.get('id')}" if el.get("id") else ""),
                    )
                )
        elif name == "table":
            rows = []
            for tr in el.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
                rows.append(" | ".join(cells))
            text = "\n".join(r for r in rows if r.strip())
            if text:
                raw.append(
                    RawBlock(
                        section_path=" / ".join(section_parts) or "ROOT",
                        text=text,
                        block_type="table",
                        source_locator=_dom_path(el) + (f"#{el.get('id')}" if el.get("id") else ""),
                    )
                )

    # Avoid double-counting nested NavigableString walks — we only used Tag names above.
    _ = NavigableString
    return to_source_blocks(raw, policy_id=policy_id, document_hash=document_hash_bytes(data))
