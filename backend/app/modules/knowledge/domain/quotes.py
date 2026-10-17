"""Quote validation — the guard against hallucinated evidence (SPEC 7.5, D-044).

A quote from the LLM is searched in the referenced fragment after normalization
(lower case, ё→е, collapsed spaces, no punctuation at the edges) with
rapidfuzz partial_ratio >= 90. What we store is the matched span of the ORIGINAL text.
"""

from dataclasses import dataclass

from rapidfuzz import fuzz

MATCH_THRESHOLD = 90.0
MIN_QUOTE_WORDS = 3
MIN_QUOTE_CHARS = 15
_EDGE = " \t\n.,;:!?\"'«»„“”()[]—–-…"


@dataclass(frozen=True)
class QuoteMatch:
    text: str  # the span of the original fragment text
    score: float


def _fold(ch: str) -> str:
    ch = ch.lower()
    return "е" if ch == "ё" else ch


def normalize(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch.isspace():
            if out and out[-1] != " ":
                out.append(" ")
        else:
            out.append(_fold(ch))
    return "".join(out).strip(_EDGE)


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalized text and, for each of its characters, the index in the original."""
    chars: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace():
            if chars and chars[-1] != " ":
                chars.append(" ")
                index.append(i)
        else:
            chars.append(_fold(ch))
            index.append(i)
    while chars and chars[-1] == " ":
        chars.pop()
        index.pop()
    return "".join(chars), index


def is_quotable(quote: str) -> bool:
    norm = normalize(quote)
    return len(norm) >= MIN_QUOTE_CHARS and len(norm.split()) >= MIN_QUOTE_WORDS


def find_quote(quote: str, text: str) -> QuoteMatch | None:
    if not is_quotable(quote):
        return None
    needle = normalize(quote)
    haystack, index = _normalize_with_map(text)
    if not haystack:
        return None

    if needle in haystack:
        start, end, score = haystack.index(needle), haystack.index(needle) + len(needle), 100.0
    elif len(needle) > len(haystack):
        # The "quote" is longer than the whole fragment: accept only if it is the fragment itself.
        score = fuzz.ratio(needle, haystack)
        if score < MATCH_THRESHOLD:
            return None
        start, end = 0, len(haystack)
    else:
        alignment = fuzz.partial_ratio_alignment(needle, haystack, score_cutoff=MATCH_THRESHOLD)
        if alignment is None:
            return None
        start, end, score = alignment.dest_start, alignment.dest_end, alignment.score

    begin, finish = index[start], index[end - 1] + 1
    # A fuzzy alignment may cut a word: extend the span to whole words of the original.
    while begin > 0 and text[begin - 1].isalnum():
        begin -= 1
    while finish < len(text) and text[finish].isalnum():
        finish += 1
    return QuoteMatch(text=text[begin:finish].strip(_EDGE), score=score)
