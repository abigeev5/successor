"""Personal data on a screenshot (SPEC 7.6.1): which OCR word boxes to blur.

Regular expressions run over each text line (OCR splits «+7 (912) 345-67-89» into several words);
names come from an injected NER function, so this module stays pure and testable.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class PiiKind(StrEnum):
    PHONE = "phone"
    EMAIL = "email"
    SNILS = "snils"
    CARD = "card"
    PASSPORT = "passport"
    INN = "inn"
    PERSON = "person"


class Box(Protocol):
    @property
    def text(self) -> str: ...
    @property
    def x(self) -> int: ...
    @property
    def y(self) -> int: ...
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def line(self) -> str | None: ...


@dataclass(frozen=True)
class PiiHit:
    kind: PiiKind
    text: str
    boxes: tuple[int, ...]  # indexes in the OCR box list


# Text → [(start, end)] of person names (natasha in the app, a stub in tests).
PersonFinder = Callable[[str], list[tuple[int, int]]]

_D = r"(?<!\d)"
_ND = r"(?!\d)"
PATTERNS: list[tuple[PiiKind, re.Pattern[str]]] = [
    (PiiKind.EMAIL, re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    (PiiKind.PHONE, re.compile(_D + r"(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}" + _ND)),
    (PiiKind.SNILS, re.compile(_D + r"\d{3}-\d{3}-\d{3}[\s-]\d{2}" + _ND)),
    (PiiKind.CARD, re.compile(_D + r"(?:\d[ -]?){15}\d" + _ND)),
    (PiiKind.PASSPORT, re.compile(_D + r"\d{2}\s?\d{2}\s?\d{6}" + _ND)),
    (PiiKind.INN, re.compile(_D + r"(?:\d{12}|\d{10})" + _ND)),
]


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _valid(kind: PiiKind, text: str) -> bool:
    if kind is PiiKind.CARD:
        return luhn_ok(re.sub(r"\D", "", text))
    return True


def group_lines(boxes: Sequence[Box]) -> list[list[int]]:
    """Box indexes by text line, left to right. Uses the OCR line key, or geometry without it."""
    lines: dict[str, list[int]] = {}
    if boxes and all(b.line for b in boxes):
        for i, b in enumerate(boxes):
            lines.setdefault(b.line or "", []).append(i)
        grouped = list(lines.values())
    else:
        grouped = []
        bottom = -1
        for i in sorted(range(len(boxes)), key=lambda i: boxes[i].y + boxes[i].height / 2):
            center = boxes[i].y + boxes[i].height / 2
            if grouped and center <= bottom:
                grouped[-1].append(i)
                bottom = max(bottom, boxes[i].y + boxes[i].height)
            else:
                grouped.append([i])
                bottom = boxes[i].y + boxes[i].height
    return [sorted(line, key=lambda i: boxes[i].x) for line in grouped]


def _join(boxes: Sequence[Box], line: list[int]) -> tuple[str, list[tuple[int, int, int]]]:
    """Line text and (start, end, box index) for every word in it."""
    parts: list[str] = []
    spans: list[tuple[int, int, int]] = []
    pos = 0
    for i in line:
        if parts:
            pos += 1
        spans.append((pos, pos + len(boxes[i].text), i))
        parts.append(boxes[i].text)
        pos += len(boxes[i].text)
    return " ".join(parts), spans


def _covered(spans: list[tuple[int, int, int]], start: int, end: int) -> tuple[int, ...]:
    return tuple(i for s, e, i in spans if s < end and start < e)


def find_pii(boxes: Sequence[Box], find_persons: PersonFinder | None = None) -> list[PiiHit]:
    hits: list[PiiHit] = []
    texts: list[str] = []
    all_spans: list[tuple[int, int, int]] = []
    offset = 0
    for line in group_lines(boxes):
        text, spans = _join(boxes, line)
        for kind, pattern in PATTERNS:
            for m in pattern.finditer(text):
                if _valid(kind, m.group()):
                    hits.append(PiiHit(kind, m.group(), _covered(spans, m.start(), m.end())))
        texts.append(text)
        all_spans += [(s + offset, e + offset, i) for s, e, i in spans]
        offset += len(text) + 1  # "\n" between lines
    if find_persons is not None and any(texts):
        page = "\n".join(texts)
        for start, end in find_persons(page):
            hits.append(PiiHit(PiiKind.PERSON, page[start:end], _covered(all_spans, start, end)))
    return [h for h in hits if h.boxes]
