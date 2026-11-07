import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.modules.org.models import HolderLevel, ProcessFrequency


class HolderOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    level: HolderLevel


class ProcessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_unit_id: uuid.UUID
    name: str
    description: str
    frequency: ProcessFrequency
    criticality: int
    holders: list[HolderOut] = []


class ProcessCreate(BaseModel):
    org_unit_id: uuid.UUID | None = None  # default: the manager's own unit
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    frequency: ProcessFrequency = ProcessFrequency.ADHOC
    criticality: int = Field(default=2, ge=1, le=3)


class ProcessUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    frequency: ProcessFrequency | None = None
    criticality: int | None = Field(default=None, ge=1, le=3)


class HolderSet(BaseModel):
    user_id: uuid.UUID
    level: HolderLevel
