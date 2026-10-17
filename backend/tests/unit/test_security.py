import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("demo1234")
    assert hashed != "demo1234"
    assert verify_password(hashed, "demo1234")
    assert not verify_password(hashed, "demo12345")


def test_verify_password_with_broken_hash_is_false() -> None:
    assert not verify_password("not-a-hash", "demo1234")


def test_token_roundtrip() -> None:
    settings = Settings(jwt_secret="test-secret-one-0123456789abcdef")
    user_id = uuid.uuid4()
    assert decode_access_token(create_access_token(user_id, settings), settings) == user_id


def test_token_with_other_secret_is_rejected() -> None:
    token = create_access_token(uuid.uuid4(), Settings(jwt_secret="test-secret-one-0123456789abcdef"))
    assert decode_access_token(token, Settings(jwt_secret="test-secret-two-0123456789abcdef")) is None


def test_expired_token_is_rejected() -> None:
    settings = Settings(jwt_secret="test-secret-one-0123456789abcdef", jwt_ttl_hours=12)
    token = create_access_token(uuid.uuid4(), settings, now=datetime.now(UTC) - timedelta(hours=13))
    assert decode_access_token(token, settings) is None


def test_garbage_token_is_rejected() -> None:
    assert decode_access_token("garbage", Settings(jwt_secret="test-secret-one-0123456789abcdef")) is None
