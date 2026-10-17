import uuid
from datetime import datetime

from pydantic import BaseModel

from app.modules.recordings.models import RecordingStage, RecordingStatus


class StepOut(BaseModel):
    id: uuid.UUID
    idx: int
    title: str
    action: str
    rationale: str | None
    start_ms: int
    end_ms: int
    screenshot_asset_id: uuid.UUID | None
    screenshot_blurred: bool


class RecordingBrief(BaseModel):
    id: uuid.UUID
    handover_id: uuid.UUID
    process_id: uuid.UUID | None
    title: str
    status: RecordingStatus
    stage: RecordingStage | None
    error: str | None
    duration_ms: int | None
    created_at: datetime


class RecordingOut(RecordingBrief):
    video_asset_id: uuid.UUID
    steps: list[StepOut]
    card_id: uuid.UUID | None  # the procedure draft made from the steps
    card_status: str | None
