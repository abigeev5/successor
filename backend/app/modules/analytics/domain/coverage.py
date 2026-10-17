"""Coverage of a process by approved cards (SPEC 7.9) and the «processes × aspects» matrix. Pure.

An aspect is covered when there is at least one approved card of a type that covers it (SPEC 7.5).
coverage_approved = covered aspects / applicable aspects (aspects marked `not_applicable` are excluded).
"""

from collections.abc import Iterable
from typing import Literal

from app.modules.interview.domain.aspects import ASPECT_KEYS
from app.modules.knowledge.domain.card_types import CARD_TYPE_ASPECTS, CardType

CellStatus = Literal["covered", "partial", "missing", "not_applicable"]


def aspects_covered_by(card_types: Iterable[CardType]) -> set[str]:
    covered: set[str] = set()
    for card_type in card_types:
        covered.update(CARD_TYPE_ASPECTS[card_type])
    return covered


def coverage_approved(card_types: Iterable[CardType], not_applicable: set[str]) -> float:
    applicable = [key for key in ASPECT_KEYS if key not in not_applicable]
    if not applicable:
        return 1.0  # nothing left to pass on
    covered = aspects_covered_by(card_types)
    return sum(1 for key in applicable if key in covered) / len(applicable)


def matrix_cell(
    aspect: str, covered_by_cards: set[str], interview_status: str, not_applicable: bool
) -> CellStatus:
    """covered — there is an approved card; partial — told in the interview, no approved card yet."""
    if not_applicable:
        return "not_applicable"
    if aspect in covered_by_cards:
        return "covered"
    if interview_status in ("partial", "covered"):
        return "partial"
    return "missing"
