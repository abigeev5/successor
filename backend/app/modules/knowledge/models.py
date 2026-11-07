import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk, str_enum
from app.modules.knowledge.domain.card_types import CardType
from app.modules.knowledge.domain.sources import CardOrigin, SourceType


class CardStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class KnowledgeCard(UUIDPk, Timestamps, Base):
    __tablename__ = "knowledge_cards"
    __table_args__ = (Index("ix_knowledge_cards_handover_status", "handover_id", "status"),)

    handover_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("handovers.id", ondelete="CASCADE"))
    process_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processes.id", ondelete="SET NULL"))
    type: Mapped[CardType] = mapped_column(str_enum(CardType, "card_type"))
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    body_md: Mapped[str] = mapped_column(Text, default="")
    applies_when: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CardStatus] = mapped_column(str_enum(CardStatus, "card_status"), default=CardStatus.DRAFT)
    archived_reason: Mapped[str | None] = mapped_column(String(40))  # source_deleted | merged
    reject_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)
    origin: Mapped[CardOrigin] = mapped_column(str_enum(CardOrigin, "card_origin"))
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_cards.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_seconds: Mapped[int] = mapped_column(default=0)


class CardSource(UUIDPk, Base):
    __tablename__ = "card_sources"
    __table_args__ = (Index("ix_card_sources_source", "source_type", "source_id"),)

    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_cards.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[SourceType] = mapped_column(str_enum(SourceType, "source_type"))
    source_id: Mapped[uuid.UUID]
    quote: Mapped[str] = mapped_column(Text)
    start_ms: Mapped[int | None]
    end_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CardRevision(UUIDPk, Base):
    """Snapshot of a card before an edit."""

    __tablename__ = "card_revisions"

    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_cards.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    type: Mapped[CardType] = mapped_column(str_enum(CardType, "card_type"))
    process_id: Mapped[uuid.UUID | None]
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    body_md: Mapped[str] = mapped_column(Text)
    applies_when: Mapped[str | None] = mapped_column(Text)
    edited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
