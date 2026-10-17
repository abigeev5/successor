import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.gaps.models import GapStatus


class GapOut(BaseModel):
    id: uuid.UUID
    handover_id: uuid.UUID
    question: str
    status: GapStatus
    asked_by_name: str | None
    assignee_id: uuid.UUID | None
    assignee_name: str | None
    answer_text: str | None
    answered_card_id: uuid.UUID | None
    answer_on_review: bool  # the expert answered, the card waits for approval
    created_at: datetime
    answered_at: datetime | None


class GapCreate(BaseModel):
    handover_id: uuid.UUID
    question: str = Field(min_length=2, max_length=2000)
    qa_log_id: uuid.UUID | None = None


class GapAnswerIn(BaseModel):
    text: str = Field(min_length=2, max_length=10000)


class GapAssignIn(BaseModel):
    assignee_id: uuid.UUID
