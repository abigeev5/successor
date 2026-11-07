"""Test settings: fake providers, a separate test database. Set before `app` is imported."""

import os

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://preemnik:preemnik@localhost:5432/preemnik_test"
)
os.environ.update(
    DATABASE_URL=TEST_DATABASE_URL,
    JWT_SECRET="test-secret-0123456789abcdef0123456789",
    DEMO_MODE="true",
    OFFLINE_MODE="false",
    LLM_PROVIDER="fake",
    EMBEDDINGS_PROVIDER="fake",
    ASR_PROVIDER="fake",
    OCR_ENGINE="fake",
    VLM_ENABLED="false",
)

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()
