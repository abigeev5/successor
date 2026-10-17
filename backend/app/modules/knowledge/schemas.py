import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.knowledge.domain.card_types import CardType
from app.modules.knowledge.domain.sources import CardOrigin, SourceType
from app.modules.knowledge.models import CardStatus


class CardListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    handover_id: uuid.UUID
    process_id: uuid.UUID | None
    type: CardType
    title: str
    summary: str
    status: CardStatus
    origin: CardOrigin
    version: int
    duplicate_of: uuid.UUID | None
    updated_at: datetime


class SourceOut(BaseModel):
    id: uuid.UUID
    source_type: SourceType
    source_id: uuid.UUID
    quote: str
    start_ms: int | None
    end_ms: int | None
    label: str
    context: str | None  # hidden from successors
    link: dict[str, str] | None
    available: bool  # false if the source was deleted


class CardDetail(CardListItem):
    body_md: str
    applies_when: str | None
    archived_reason: str | None
    reject_reason: str | None
    approved_at: datetime | None
    review_seconds: int
    sources: list[SourceOut] = []


class CardEdit(BaseModel):
    type: CardType | None = None
    process_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=5000)
    body_md: str | None = Field(default=None, max_length=50000)
    applies_when: str | None = Field(default=None, max_length=5000)


class ApproveIn(BaseModel):
    edits: CardEdit | None = None
    review_seconds: int = Field(default=0, ge=0, le=24 * 3600)


class RejectIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
    review_seconds: int = Field(default=0, ge=0, le=24 * 3600)


class MergeIn(BaseModel):
    into_card_id: uuid.UUID


class CardCreate(BaseModel):
    handover_id: uuid.UUID
    type: CardType
    process_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(default="", max_length=5000)
    body_md: str = Field(default="", max_length=50000)
    applies_when: str | None = Field(default=None, max_length=5000)
