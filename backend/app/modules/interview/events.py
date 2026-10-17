import uuid
from dataclasses import dataclass

from app.core.events import Event


@dataclass(frozen=True)
class InterviewTurnCompleted(Event):
    session_id: uuid.UUID
    handover_id: uuid.UUID
    user_id: uuid.UUID
    step: str
    voice: bool


@dataclass(frozen=True)
class InterviewSessionFinished(Event):
    session_id: uuid.UUID
    handover_id: uuid.UUID
    user_id: uuid.UUID
    active_seconds: int
