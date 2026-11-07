"""Splitting an approved card into chunks for the index (~500 tokens, by paragraphs / steps)."""

import re

CHUNK_CHARS = 2000  # ≈ 500 tokens at ~4 characters per token
_BLOCKS = re.compile(r"\n\s*\n|\n(?=\s*(?:\d+[.)]|[-*•])\s)")


def split_blocks(body: str) -> list[str]:
    """Paragraphs and list items (numbered steps stay separate blocks)."""
    return [b.strip() for b in _BLOCKS.split(body) if b and b.strip()]


def chunk_card(
    title: str, summary: str, body_md: str, applies_when: str | None = None, max_chars: int = CHUNK_CHARS
) -> list[str]:
    """Every chunk starts with the card title, so a step found alone still says what it belongs to."""
    header = title.strip()
    lead = "\n".join(
        p for p in (summary.strip(), f"Когда применять: {applies_when.strip()}" if applies_when else "") if p
    )
    chunks: list[str] = []
    current: list[str] = [lead] if lead else []
    size = sum(len(p) for p in current)
    for block in split_blocks(body_md):
        if current and size + len(block) > max_chars:
            chunks.append("\n".join([header, *current]))
            current, size = [], 0
        current.append(block)
        size += len(block)
    if current or not chunks:
        chunks.append("\n".join([header, *current]))
    return chunks
