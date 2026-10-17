import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk, str_enum


class OrgUnit(UUIDPk, Timestamps, Base):
    __tablename__ = "org_units"

    name: Mapped[str] = mapped_column(String(200), unique=True)


class ProcessFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    ADHOC = "adhoc"


class Process(UUIDPk, Timestamps, Base):
    __tablename__ = "processes"
    __table_args__ = (CheckConstraint("criticality BETWEEN 1 AND 3", name="criticality_range"),)

    org_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org_units.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    frequency: Mapped[ProcessFrequency] = mapped_column(
        str_enum(ProcessFrequency, "process_frequency"), default=ProcessFrequency.ADHOC
    )
    criticality: Mapped[int] = mapped_column(default=2)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class HolderLevel(StrEnum):
    OWNER = "owner"
    KNOWS = "knows"
    LEARNING = "learning"


class ProcessHolder(Base):
    """Who knows a process — the input for the bus factor (SPEC, 7.9). Composite PK (D-021)."""

    __tablename__ = "process_holders"

    process_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processes.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    level: Mapped[HolderLevel] = mapped_column(str_enum(HolderLevel, "holder_level"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
