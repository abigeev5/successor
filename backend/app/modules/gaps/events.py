import uuid
from dataclasses import dataclass

from app.core.events import Event


@dataclass(frozen=True)
class GapCreated(Event):
    gap_id: uuid.UUID
    handover_id: uuid.UUID
    user_id: uuid.UUID | None
    from_refusal: bool


@dataclass(frozen=True)
class GapAnswered(Event):
    """The answer card was approved: the successor gets the answer."""

    gap_id: uuid.UUID
    handover_id: uuid.UUID
    user_id: uuid.UUID | None
