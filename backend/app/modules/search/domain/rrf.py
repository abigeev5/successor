"""Reciprocal Rank Fusion of vector and full-text rankings (k = 60)."""

from collections.abc import Hashable, Sequence
from typing import TypeVar

K = TypeVar("K", bound=Hashable)
RRF_K = 60


def rrf(rankings: Sequence[Sequence[K]], k: int = RRF_K) -> list[tuple[K, float]]:
    """Each ranking is a list of ids, best first. Returns ids by fused score, best first."""
    scores: dict[K, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: -pair[1])


def group_by_card(chunk_ids: Sequence[K], card_of: dict[K, K], limit: int) -> list[K]:
    """Card ids in the order of their best chunk, at most `limit`."""
    cards: list[K] = []
    for chunk_id in chunk_ids:
        card_id = card_of[chunk_id]
        if card_id not in cards:
            cards.append(card_id)
        if len(cards) == limit:
            break
    return cards
