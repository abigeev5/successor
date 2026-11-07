from collections.abc import Awaitable, Callable

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.errors import Forbidden, NotAuthenticated
from app.core.security import AUTH_COOKIE, decode_access_token
from app.modules.identity.models import User, UserRole
from app.modules.identity.service import get_user


async def current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    token = request.cookies.get(AUTH_COOKIE)
    user_id = decode_access_token(token, settings) if token else None
    user = await get_user(db, user_id) if user_id else None
    if user is None or not user.is_active:
        raise NotAuthenticated()
    return user


def require_roles(*roles: UserRole) -> Callable[..., Awaitable[User]]:
    """Global role check. Access to a specific handover is checked by handovers.access."""

    async def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise Forbidden()
        return user

    return dependency
