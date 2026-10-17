import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings

AUTH_COOKIE = "access_token"
_ALGORITHM = "HS256"
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, settings: Settings, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=settings.jwt_ttl_hours)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> uuid.UUID | None:
    """Returns the user id, or None if the token is invalid or expired."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
