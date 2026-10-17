import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import AUTH_COOKIE, create_access_token
from app.modules.identity import service
from app.modules.identity.deps import current_user, require_roles
from app.modules.identity.models import User, UserRole
from app.modules.identity.schemas import LoginIn, UserBrief, UserCreate, UserOut, UserUpdate

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])
admin_router = APIRouter(prefix="/admin/users", tags=["admin"])


@auth_router.post("/login", response_model=UserOut)
async def login(
    data: LoginIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    user = await service.authenticate(db, data.email, data.password)
    response.set_cookie(
        AUTH_COOKIE,
        create_access_token(user.id, settings),
        max_age=settings.jwt_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return user


@auth_router.post("/logout", status_code=204)
async def logout(response: Response, settings: Settings = Depends(get_settings)) -> None:
    response.delete_cookie(
        AUTH_COOKIE, path="/", httponly=True, samesite="lax", secure=settings.cookie_secure
    )


@auth_router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> User:
    return user


_admin = require_roles(UserRole.ADMIN)


@admin_router.get("", response_model=list[UserOut])
async def list_users(_: User = Depends(_admin), db: AsyncSession = Depends(get_db)) -> list[User]:
    return await service.list_users(db)


@admin_router.post("", response_model=UserOut, status_code=201)
async def create_user(
    data: UserCreate, actor: User = Depends(_admin), db: AsyncSession = Depends(get_db)
) -> User:
    return await service.create_user(db, data, actor_id=actor.id)


@admin_router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID, data: UserUpdate, actor: User = Depends(_admin), db: AsyncSession = Depends(get_db)
) -> User:
    return await service.update_user(db, user_id, data, actor_id=actor.id)


@users_router.get("", response_model=list[UserBrief])
async def directory(
    role: UserRole | None = None,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    """People a manager can pick as expert or successor: their org unit (admin: everyone)."""
    org_unit_id = None if user.role is UserRole.ADMIN else user.org_unit_id
    return await service.directory(
        db, org_unit_id=org_unit_id, role=role, restrict=user.role is not UserRole.ADMIN
    )
