import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.interview.domain.state import ProcessCandidate
from app.modules.interview.models import MessageRole, SessionStatus
from app.modules.org.models import ProcessFrequency


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    seq: int
    role: MessageRole
    content: str
    has_audio: bool = False
    meta: dict[str, Any] = {}
    created_at: datetime


class AspectOut(BaseModel):
    key: str
    label: str
    status: str
    not_applicable: bool


class ProcessCoverageOut(BaseModel):
    process_id: uuid.UUID
    name: str
    criticality: int
    coverage: float
    aspects: list[AspectOut]


class SessionBrief(BaseModel):
    id: uuid.UUID
    handover_id: uuid.UUID
    status: SessionStatus
    phase: str
    started_at: datetime
    finished_at: datetime | None
    active_seconds: int
    messages_count: int


class SessionOut(SessionBrief):
    current_process_id: uuid.UUID | None
    candidates: list[ProcessCandidate]
    messages: list[MessageOut]
    coverage: list[ProcessCoverageOut]


class StartIn(BaseModel):
    handover_id: uuid.UUID


class TurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    audio_asset_id: uuid.UUID | None = None


class CandidateDecision(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    frequency: ProcessFrequency = ProcessFrequency.ADHOC
    criticality: int = Field(default=2, ge=1, le=3)
    include: bool = True


class ConfirmIn(BaseModel):
    items: list[CandidateDecision]


class AudioOut(BaseModel):
    asset_id: uuid.UUID
    text: str
    duration_ms: int | None
