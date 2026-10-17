import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk, str_enum


class SessionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    FINISHED = "finished"


class MessageRole(StrEnum):
    INTERVIEWER = "interviewer"
    EXPERT = "expert"


class InterviewSession(UUIDPk, Timestamps, Base):
    __tablename__ = "interview_sessions"

    handover_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("handovers.id", ondelete="CASCADE"), index=True)
    expert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[SessionStatus] = mapped_column(
        str_enum(SessionStatus, "session_status"), default=SessionStatus.ACTIVE
    )
    phase: Mapped[str] = mapped_column(String(20), default="intro")
    state_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_seconds: Mapped[int] = mapped_column(default=0)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # D-043


class InterviewMessage(UUIDPk, Base):
    __tablename__ = "interview_messages"
    __table_args__ = (UniqueConstraint("session_id", "seq"),)

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"))
    seq: Mapped[int]
    role: Mapped[MessageRole] = mapped_column(str_enum(MessageRole, "message_role"))
    content: Mapped[str] = mapped_column(Text)
    audio_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # kind, process_id, aspect, probe_type
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessAspect(Base):
    """Coverage of a process aspect within a handover, shared by all sessions (D-003, D-040)."""

    __tablename__ = "process_aspects"

    handover_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handovers.id", ondelete="CASCADE"), primary_key=True
    )
    process_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processes.id", ondelete="CASCADE"), primary_key=True
    )
    aspect: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="missing")
    not_applicable: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
