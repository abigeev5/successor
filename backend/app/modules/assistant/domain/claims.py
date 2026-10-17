"""Splitting an answer into claims and assembling it back without unsupported ones (SPEC 7.8).

A claim is a sentence (or a list item) with citations [n]. Sentences without citations are
unsupported — except notes: a lead-in ending with «:» or a remark about what the base lacks
(«В базе нет сведений о …»), which the answer prompt asks for in partial answers (D-048).
"""

import re
from dataclasses import dataclass, field

_CITATION = re.compile(r"\[(\d+)\]")
_ITEM = re.compile(r"^(\s*(?:\d+[.)]|[-*•])\s+)(.*)$")
# Citations written after the full stop («…отправить. [1]») move before it («…отправить [1].»).
_CITE_AFTER_STOP = re.compile(r"([.!?…])\s*(\[\d+\](?:\s*\[\d+\])*)")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[А-ЯЁA-Z0-9«\"(])")
_ABSENCE = re.compile(
    r"(в (базе|источниках|карточках)[^.]*\b(нет|не\s+(указан|описан|сказано|говорится)))"
    r"|(нет (информации|сведений|данных))|(не (нашлось|найдено|удалось найти))",
    re.IGNORECASE,
)


@dataclass
class Sentence:
    id: int
    text: str
    citations: tuple[int, ...]
    note: str  # "" — a claim; "lead" — «Порядок такой:»; "absence" — «В базе нет сведений о …»

    @property
    def is_note(self) -> bool:
        return bool(self.note)


@dataclass
class Line:
    marker: str  # «1. », «- » or "" for a paragraph line
    sentences: list[Sentence] = field(default_factory=list)


def _note_kind(text: str, citations: tuple[int, ...]) -> str:
    if citations:
        return ""
    if _ABSENCE.search(text):
        return "absence"
    return "lead" if text.rstrip().endswith(":") else ""


def parse_answer(answer: str) -> list[Line]:
    lines: list[Line] = []
    next_id = 0
    for raw in answer.strip().splitlines():
        if not raw.strip():
            lines.append(Line(marker=""))  # keeps paragraph breaks
            continue
        match = _ITEM.match(raw)
        marker, body = (match.group(1), match.group(2)) if match else ("", raw.strip())
        body = _CITE_AFTER_STOP.sub(lambda m: f" {m.group(2)}{m.group(1)}", body)
        line = Line(marker=marker)
        for part in _SENTENCE_END.split(body):
            part = part.strip()
            if not part:
                continue
            citations = tuple(int(n) for n in _CITATION.findall(part))
            line.sentences.append(Sentence(next_id, part, citations, _note_kind(part, citations)))
            next_id += 1
        lines.append(line)
    return lines


def claims(lines: list[Line]) -> list[Sentence]:
    """Sentences that must be checked (everything except notes)."""
    return [s for line in lines for s in line.sentences if not s.is_note]


def assemble(lines: list[Line], supported: set[int]) -> str:
    """The answer with only supported claims and notes. Numbered lists are renumbered."""
    out: list[str] = []
    number = 0
    for line in lines:
        kept = [s.text for s in line.sentences if s.is_note or s.id in supported]
        if not line.sentences:
            if out and out[-1] != "":
                out.append("")
            number = 0
            continue
        if not kept:
            continue
        marker = line.marker
        if re.match(r"\s*\d+[.)]", marker):
            number += 1
            marker = re.sub(r"\d+", str(number), marker, count=1)
        else:
            number = 0
        out.append(marker + " ".join(kept))
    return "\n".join(out).strip()


def mentions_absence(lines: list[Line]) -> bool:
    """The answer says that part of it is missing from the base → a partial answer."""
    return any(s.note == "absence" for line in lines for s in line.sentences)


def cited(lines: list[Line], supported: set[int]) -> list[int]:
    """Source numbers cited by the kept claims, in order of first use."""
    numbers: list[int] = []
    for line in lines:
        for sentence in line.sentences:
            if sentence.id in supported:
                numbers += [n for n in sentence.citations if n not in numbers]
    return numbers
