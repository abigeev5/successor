import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.modules.handovers.domain.policy import HandoverRole
from app.modules.handovers.models import HandoverReason, HandoverStatus
from app.modules.identity.schemas import UserBrief
from app.modules.org.models import ProcessFrequency


class ProcessBrief(BaseModel):
    id: uuid.UUID
    name: str
    criticality: int
    frequency: ProcessFrequency


class HandoverOut(BaseModel):
    id: uuid.UUID
    org_unit_id: uuid.UUID
    org_unit_name: str
    manager: UserBrief
    experts: list[UserBrief]
    successors: list[UserBrief]
    reason: HandoverReason
    deadline: date | None
    status: HandoverStatus
    processes: list[ProcessBrief]
    created_at: datetime
    my_role: HandoverRole | None = None


class HandoverCreate(BaseModel):
    org_unit_id: uuid.UUID | None = None  # default: the manager's unit
    expert_id: uuid.UUID
    successor_id: uuid.UUID | None = None
    reason: HandoverReason
    deadline: date | None = None
    process_ids: list[uuid.UUID] = Field(default_factory=list)


class HandoverUpdate(BaseModel):
    reason: HandoverReason | None = None
    deadline: date | None = None
    status: HandoverStatus | None = None
    successor_id: uuid.UUID | None = None
    process_ids: list[uuid.UUID] | None = None
