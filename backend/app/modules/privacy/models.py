import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPk


class Consent(UUIDPk, Base):
    """Consent of an employee to recording within one handover (SPEC 7.3)."""

    __tablename__ = "consents"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    handover_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("handovers.id", ondelete="CASCADE"), index=True)
    text_version: Mapped[str] = mapped_column(String(20))
    text_hash: Mapped[str] = mapped_column(String(64))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
