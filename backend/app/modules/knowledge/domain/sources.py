"""Knowledge sources in general (docs/architecture.md, 5.1).

Extraction, quote validation, the review screen and assistant citations work with these types,
not with interviews or recordings directly. A new kind of source = a new module that builds a
SourceDocument and registers a SourceResolver; this module does not change.
"""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class SourceType(StrEnum):
    INTERVIEW_MESSAGE = "interview_message"
    TRANSCRIPT_SEGMENT = "transcript_segment"
    RECORDING_STEP = "recording_step"
    GAP_ANSWER = "gap_answer"


class CardOrigin(StrEnum):
    INTERVIEW = "interview"
    RECORDING = "recording"
    GAP_ANSWER = "gap_answer"
    MANUAL = "manual"


@dataclass(frozen=True)
class SourceRef:
    type: SourceType
    id: uuid.UUID


@dataclass(frozen=True)
class SourceFragment:
    """A piece of text a quote may point to."""

    ref: SourceRef
    text: str
    label: str  # for people: «Реплика 12», «03:15–03:40»
    start_ms: int | None = None
    end_ms: int | None = None
    context: str | None = None  # e.g. the interviewer's question before the answer; not evidence


@dataclass(frozen=True)
class SourceDocument:
    handover_id: uuid.UUID
    origin: CardOrigin
    fragments: list[SourceFragment] = field(default_factory=list)
