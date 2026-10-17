"""Splitting a source document into LLM windows (SPEC 7.5: ~3000 tokens, overlap of one fragment)."""

CHARS_PER_TOKEN = 4  # rough estimate, no tokenizer (D-038)
WINDOW_CHARS = 3000 * CHARS_PER_TOKEN


def make_windows(lengths: list[int], max_chars: int = WINDOW_CHARS) -> list[range]:
    """Index ranges of fragments; consecutive windows share one fragment.

    A single fragment longer than max_chars still gets its own window.
    """
    windows: list[range] = []
    start = 0
    while start < len(lengths):
        end, size = start, 0
        while end < len(lengths) and (end == start or size + lengths[end] <= max_chars):
            size += lengths[end]
            end += 1
        windows.append(range(start, end))
        if end >= len(lengths):
            break
        start = end - 1 if end - 1 > start else end
    return windows
