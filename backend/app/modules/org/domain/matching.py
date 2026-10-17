"""Fuzzy matching of process names: the LLM says «отчет по контингенту», the process is
«Отчёт о движении контингента». Russian inflection is handled by a crude stem (first 5 letters)."""

import re
import uuid
from collections.abc import Iterable

from rapidfuzz import fuzz

MATCH_THRESHOLD = 80
AMBIGUITY_MARGIN = 5  # two candidates this close → do not guess
_STOP_WORDS = {"о", "об", "по", "в", "во", "на", "для", "и", "с", "со", "к", "ко", "от", "из", "за", "при"}


def normalize_name(name: str) -> str:
    name = name.lower().replace("ё", "е")
    name = re.sub(r"[^\w\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def stem_name(name: str) -> str:
    return " ".join(word[:5] for word in normalize_name(name).split() if word not in _STOP_WORDS)


def match_name(name: str | None, candidates: Iterable[tuple[uuid.UUID, str]]) -> uuid.UUID | None:
    """Best candidate id with similarity >= MATCH_THRESHOLD; None if nothing fits or it is ambiguous."""
    query = stem_name(name or "")
    if not query:
        return None
    scored = sorted(
        (
            (fuzz.WRatio(query, stem_name(candidate_name)), candidate_id)
            for candidate_id, candidate_name in candidates
        ),
        key=lambda item: -item[0],
    )
    if not scored or scored[0][0] < MATCH_THRESHOLD:
        return None
    if len(scored) > 1 and scored[1][0] >= MATCH_THRESHOLD and scored[0][0] - scored[1][0] < AMBIGUITY_MARGIN:
        return None
    return scored[0][1]
