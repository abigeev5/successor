import uuid
from dataclasses import dataclass

from app.core.events import Event


@dataclass(frozen=True)
class RecordingUploaded(Event):
    recording_id: uuid.UUID
    handover_id: uuid.UUID
    user_id: uuid.UUID | None
    size_bytes: int


@dataclass(frozen=True)
class RecordingProcessed(Event):
    recording_id: uuid.UUID
    handover_id: uuid.UUID
    duration_ms: int
    steps: int
    blurred_screenshots: int
