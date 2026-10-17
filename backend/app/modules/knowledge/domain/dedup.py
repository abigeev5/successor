"""Duplicate detection by embedding similarity (SPEC 7.5: cosine >= 0.9)."""

import uuid

DUPLICATE_THRESHOLD = 0.9


def cosine(a: list[float], b: list[float]) -> float:
    """Vectors are L2-normalized by providers, so the dot product is the cosine."""
    return sum(x * y for x, y in zip(a, b, strict=True))


def find_duplicate(
    vector: list[float], existing: list[tuple[uuid.UUID, list[float]]], threshold: float = DUPLICATE_THRESHOLD
) -> tuple[uuid.UUID, float] | None:
    best: tuple[uuid.UUID, float] | None = None
    for card_id, other in existing:
        score = cosine(vector, other)
        if score >= threshold and (best is None or score > best[1]):
            best = (card_id, score)
    return best
