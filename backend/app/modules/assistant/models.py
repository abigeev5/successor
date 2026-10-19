import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ARRAY, DateTime, ForeignKey, Index, SmallInteger, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPk, str_enum


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    PARTIAL = "partial"
    REFUSED = "refused"


class QaLog(UUIDPk, Base):
    """Every question and what the assistant did with it."""

    __tablename__ = "qa_logs"
    __table_args__ = (Index("ix_qa_logs_handover_created", "handover_id", "created_at"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    handover_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("handovers.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[AnswerStatus] = mapped_column(str_enum(AnswerStatus, "answer_status"))
    refusal_reason: Mapped[str | None] = mapped_column(String(40))
    verification: Mapped[str] = mapped_column(String(40))
    cited_card_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), default=list)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # [{n, card_id, title, type}]
    retrieval: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    groundedness: Mapped[float | None]
    latency_ms: Mapped[int]
    prompt_version: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(200))
    feedback: Mapped[int | None] = mapped_column(SmallInteger)  # 1 helpful, -1 not helpful
    feedback_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
