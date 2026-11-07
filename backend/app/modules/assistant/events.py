import uuid
from dataclasses import dataclass

from app.core.events import Event


@dataclass(frozen=True)
class AnswerShown(Event):
    qa_id: uuid.UUID
    handover_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    groundedness: float | None
    latency_ms: int


@dataclass(frozen=True)
class AnswerRefused(Event):
    """The base had no answer: the question becomes a gap for the expert."""

    qa_id: uuid.UUID
    handover_id: uuid.UUID
    user_id: uuid.UUID
    question: str  # in-process only; analytics must not store it
    latency_ms: int


@dataclass(frozen=True)
class AnswerFeedback(Event):
    qa_id: uuid.UUID
    handover_id: uuid.UUID
    user_id: uuid.UUID
    helpful: bool
