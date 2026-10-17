import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk, str_enum


class UserRole(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    EXPERT = "expert"
    SUCCESSOR = "successor"


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True)  # stored lower-case
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole, "user_role"))
    password_hash: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(default=True)
    # Decision D-017: a manager sees handovers of their org unit.
    org_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("org_units.id", ondelete="SET NULL"))
