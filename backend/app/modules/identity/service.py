import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotAuthenticated, NotFound
from app.core.security import hash_password, verify_password
from app.modules import audit
from app.modules.identity.models import User
from app.modules.identity.schemas import UserCreate, UserUpdate

INVALID_CREDENTIALS = "Неверный email или пароль"
# Verified when the email is unknown, so response time does not reveal which emails exist.
_DUMMY_HASH = hash_password("dummy-password")


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(db, email)
    # argon2 is CPU-bound: keep it off the event loop.
    password_ok = await asyncio.to_thread(
        verify_password, user.password_hash if user else _DUMMY_HASH, password
    )
    if user is None or not user.is_active or not password_ok:
        await audit.record(db, action="auth.login_failed", entity="user", entity_id=user.id if user else None)
        await db.commit()
        raise NotAuthenticated(INVALID_CREDENTIALS, code="invalid_credentials")
    await audit.record(db, action="auth.login", entity="user", entity_id=user.id, user_id=user.id)
    await db.commit()
    return user


async def list_users(db: AsyncSession) -> list[User]:
    return list((await db.execute(select(User).order_by(User.full_name))).scalars())


async def create_user(db: AsyncSession, data: UserCreate, *, actor_id: uuid.UUID | None) -> User:
    if await get_user_by_email(db, data.email) is not None:
        raise Conflict("Пользователь с таким email уже есть", code="email_taken")
    user = User(
        email=data.email,
        full_name=data.full_name,
        role=data.role,
        password_hash=hash_password(data.password),
        org_unit_id=data.org_unit_id,
    )
    db.add(user)
    await db.flush()
    await audit.record(db, action="user.created", entity="user", entity_id=user.id, user_id=actor_id)
    await db.commit()
    return user


async def update_user(
    db: AsyncSession, user_id: uuid.UUID, data: UserUpdate, *, actor_id: uuid.UUID | None
) -> User:
    user = await get_user(db, user_id)
    if user is None:
        raise NotFound("Пользователь не найден")
    changes = data.model_dump(exclude_unset=True)
    password = changes.pop("password", None)
    for field, value in changes.items():
        setattr(user, field, value)
    if password:
        user.password_hash = hash_password(password)
    await audit.record(
        db,
        action="user.updated",
        entity="user",
        entity_id=user.id,
        user_id=actor_id,
        meta={"fields": sorted([*changes, *(["password"] if password else [])])},
    )
    await db.commit()
    return user
