import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk, str_enum


class HandoverReason(StrEnum):
    RETIREMENT = "retirement"
    LEAVE = "leave"
    RESIGNATION = "resignation"
    TRANSFER = "transfer"
    OTHER = "other"


class HandoverStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MemberRole(StrEnum):
    EXPERT = "expert"
    SUCCESSOR = "successor"


class Handover(UUIDPk, Timestamps, Base):
    __tablename__ = "handovers"

    org_unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("org_units.id", ondelete="RESTRICT"), index=True
    )
    manager_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[HandoverReason] = mapped_column(str_enum(HandoverReason, "handover_reason"))
    deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[HandoverStatus] = mapped_column(
        str_enum(HandoverStatus, "handover_status"), default=HandoverStatus.DRAFT
    )


class HandoverMember(Base):
    """Experts and successors of a handover (decision D-002). Composite PK (D-021)."""

    __tablename__ = "handover_members"

    handover_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handovers.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[MemberRole] = mapped_column(str_enum(MemberRole, "member_role"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HandoverProcess(Base):
    __tablename__ = "handover_processes"

    handover_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handovers.id", ondelete="CASCADE"), primary_key=True
    )
    process_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processes.id", ondelete="CASCADE"), primary_key=True
    )
