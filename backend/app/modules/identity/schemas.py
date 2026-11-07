import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.identity.models import UserRole


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    local, sep, domain = value.partition("@")
    if not sep or not local or "." not in domain:
        raise ValueError("Некорректный email")
    return value


class LoginIn(BaseModel):
    # Plain str instead of EmailStr: email-validator rejects special-use domains such as demo.local.
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    org_unit_id: uuid.UUID | None


class UserCreate(BaseModel):
    email: str = Field(max_length=320)
    full_name: str = Field(min_length=1, max_length=200)
    role: UserRole
    password: str = Field(min_length=8, max_length=200)
    org_unit_id: uuid.UUID | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)
    org_unit_id: uuid.UUID | None = None


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    role: UserRole
