import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk, str_enum


class GapStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    DISMISSED = "dismissed"


class Gap(UUIDPk, Timestamps, Base):
    __tablename__ = "gaps"
    __table_args__ = (Index("ix_gaps_handover_status", "handover_id", "status"),)

    handover_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("handovers.id", ondelete="CASCADE"))
    qa_log_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("qa_logs.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[GapStatus] = mapped_column(str_enum(GapStatus, "gap_status"), default=GapStatus.OPEN)
    asked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    answer_text: Mapped[str | None] = mapped_column(Text)  # the source of the gap_answer card
    answered_card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_cards.id", ondelete="SET NULL")
    )
    answered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # card approved
