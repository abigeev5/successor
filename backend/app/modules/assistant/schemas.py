import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.assistant.models import AnswerStatus
from app.modules.knowledge.domain.card_types import CardType

# verified — every claim is confirmed; partially_removed — unconfirmed claims were removed;
# not_verified — the judge failed; degraded — no model, excerpts of the found cards; none — refusal.
Verification = Literal["verified", "partially_removed", "not_verified", "degraded", "none"]


class AskIn(BaseModel):
    handover_id: uuid.UUID
    question: str = Field(min_length=2, max_length=2000)


class SourceRef(BaseModel):
    n: int
    card_id: uuid.UUID
    title: str
    type: CardType


class AnswerOut(BaseModel):
    qa_id: uuid.UUID
    question: str
    status: AnswerStatus
    answer: str | None
    sources: list[SourceRef]
    groundedness: float | None
    verification: Verification
    refusal_reason: str | None
    forwarded_to: str | None = None  # who got the question as a gap («Я передал его …»)
    feedback: int | None
    created_at: datetime


class FeedbackIn(BaseModel):
    helpful: bool
    comment: str | None = Field(default=None, max_length=2000)
