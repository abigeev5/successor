"""Personal data on a screenshot (SPEC 7.6.1): which OCR word boxes to blur.

Regular expressions run over each text line (OCR splits «+7 (912) 345-67-89» into several words).
Names: patterns of Russian full names plus an injected NER function (natasha in the app), run per
line on words cleaned of OCR noise — on UI text NER alone misses names and glues neighbouring lines.
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
    # The domain dot is optional: OCR often reads «student.demo» as «student demo».
    (PiiKind.EMAIL, re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*")),
    (PiiKind.PHONE, re.compile(_D + r"(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}" + _ND)),
    (PiiKind.SNILS, re.compile(_D + r"\d{3}-\d{3}-\d{3}[\s-]\d{2}" + _ND)),
    (PiiKind.CARD, re.compile(_D + r"(?:\d[ -]?){15}\d" + _ND)),
    (PiiKind.PASSPORT, re.compile(_D + r"\d{2}\s?\d{2}\s?\d{6}" + _ND)),
    (PiiKind.INN, re.compile(_D + r"(?:\d{12}|\d{10})" + _ND)),
]
_NAME = r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
# «Смирнова Анна Павловна», «Ирина Сергеевна», «Петров А. В.» — on cleaned words (see `_clean`).
NAME_PATTERNS = [
    # (Surname) Name Patronymic: the patronymic ending marks a name even without a surname.
    re.compile(rf"\b(?:{_NAME} )?{_NAME} [А-ЯЁ][а-яё]+(?:вич|вна|чна|ична|оглы|кызы)\b"),
    re.compile(rf"\b{_NAME} [А-ЯЁ]\. ?[А-ЯЁ]\.(?!\w)"),
]
_EDGE_NOISE = " \t‘’'\"«»“”`,;:|()[]{}"


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


def _clean(word: str) -> str:
    """«‘Смирнова» → «Смирнова», «Павловна.» → «Павловна» (keeps the dot of an initial: «А.»)."""
    word = word.strip(_EDGE_NOISE)
    if len(word) > 2 and word.endswith("."):
        word = word[:-1]
    return word


def _join(
    boxes: Sequence[Box], line: list[int], clean: bool = False
) -> tuple[str, list[tuple[int, int, int]]]:
    """Line text and (start, end, box index) for every word in it."""
    parts: list[str] = []
    spans: list[tuple[int, int, int]] = []
    pos = 0
    for i in line:
        word = _clean(boxes[i].text) if clean else boxes[i].text
        if parts:
            pos += 1
        spans.append((pos, pos + len(word), i))
        parts.append(word)
        pos += len(word)
    return " ".join(parts), spans


def _covered(spans: list[tuple[int, int, int]], start: int, end: int) -> tuple[int, ...]:
    return tuple(i for s, e, i in spans if s < end and start < e)


def find_pii(boxes: Sequence[Box], find_persons: PersonFinder | None = None) -> list[PiiHit]:
    hits: list[PiiHit] = []
    for line in group_lines(boxes):
        text, spans = _join(boxes, line)
        for kind, pattern in PATTERNS:
            for m in pattern.finditer(text):
                if _valid(kind, m.group()):
                    hits.append(PiiHit(kind, m.group(), _covered(spans, m.start(), m.end())))
        names, name_spans = _join(boxes, line, clean=True)
        found = [(m.start(), m.end()) for p in NAME_PATTERNS for m in p.finditer(names)]
        if find_persons is not None and names.strip():
            found += find_persons(names)
        for start, end in found:
            hits.append(PiiHit(PiiKind.PERSON, names[start:end], _covered(name_spans, start, end)))
    return [h for h in hits if h.boxes]
