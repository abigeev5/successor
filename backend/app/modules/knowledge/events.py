import uuid
from dataclasses import dataclass

from app.core.events import Event


@dataclass(frozen=True)
class CardDrafted(Event):
    card_id: uuid.UUID
    handover_id: uuid.UUID
    origin: str


@dataclass(frozen=True)
class CardDropped(Event):
    """A candidate card without valid evidence."""

    handover_id: uuid.UUID
    origin: str
    reason: str


@dataclass(frozen=True)
class CardApproved(Event):
    card_id: uuid.UUID
    handover_id: uuid.UUID
    version: int
    origin: str
    edited: bool
    user_id: uuid.UUID | None
    review_seconds: int = 0  # time the expert spent on this review (`review_time`)


@dataclass(frozen=True)
class CardRejected(Event):
    card_id: uuid.UUID
    handover_id: uuid.UUID
    user_id: uuid.UUID | None
    review_seconds: int = 0


@dataclass(frozen=True)
class CardArchived(Event):
    card_id: uuid.UUID
    handover_id: uuid.UUID
    reason: str
