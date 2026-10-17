import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.assistant.models import AnswerStatus


class AskIn(BaseModel):
    handover_id: uuid.UUID
    question: str = Field(min_length=2, max_length=2000)


class SourceRef(BaseModel):
    n: int
    card_id: uuid.UUID
    title: str
    type: str


class AnswerOut(BaseModel):
    qa_id: uuid.UUID
    question: str
    status: AnswerStatus
    answer: str | None
    sources: list[SourceRef]
    groundedness: float | None
    verification: str
    refusal_reason: str | None
    forwarded_to: str | None = None  # who got the question as a gap («Я передал его …»)
    feedback: int | None
    created_at: datetime


class FeedbackIn(BaseModel):
    helpful: bool
    comment: str | None = Field(default=None, max_length=2000)
