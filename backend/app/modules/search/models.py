import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPk

# The column size is fixed by the migration; another model needs a migration + reindex.
EMBEDDING_DIM = 1024


class CardChunk(UUIDPk, Base):
    """Index of approved cards only. Rebuilt on every approval of a new card version."""

    __tablename__ = "card_chunks"
    __table_args__ = (
        Index(
            "ix_card_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_card_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_cards.id", ondelete="CASCADE"), index=True
    )
    handover_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("handovers.id", ondelete="CASCADE"), index=True)
    org_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org_units.id", ondelete="CASCADE"))
    process_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processes.id", ondelete="SET NULL"))
    card_version: Mapped[int]
    idx: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str] = mapped_column(String(200))
    tsv: Mapped[str] = mapped_column(TSVECTOR, Computed("to_tsvector('russian', text)", persisted=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
