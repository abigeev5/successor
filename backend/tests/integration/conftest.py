"""Integration tests run against a real PostgreSQL (+pgvector).

No database → tests are skipped with a reason; with REQUIRE_DB=1 (CI) → they fail (decision D-023).
"""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base, dispose_engine, get_sessionmaker
from app.wiring import wire
from tests.conftest import TEST_DATABASE_URL

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _libpq_dsn(database: str | None = None) -> str:
    url = make_url(TEST_DATABASE_URL)
    if database:
        url = url.set(database=database)
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def _prepare_database() -> None:
    name = make_url(TEST_DATABASE_URL).database
    with psycopg.connect(_libpq_dsn("postgres"), autocommit=True, connect_timeout=3) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            conn.execute(f'CREATE DATABASE "{name}"')
    with psycopg.connect(_libpq_dsn(), autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    try:
        _prepare_database()
    except psycopg.OperationalError as exc:
        safe_url = make_url(TEST_DATABASE_URL).render_as_string(hide_password=True)
        message = f"PostgreSQL недоступна ({safe_url}): {str(exc).splitlines()[0]}"
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(message)
        pytest.skip(message + " — запустите `make db` или задайте TEST_DATABASE_URL")
    command.upgrade(alembic_config(), "head")
    yield


@pytest.fixture
async def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_dir", tmp_path)
    wire()  # tests may add their own subscribers; start every test from the real wiring
    async with get_sessionmaker()() as session:
        yield session
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with get_sessionmaker()() as session:
        await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await session.commit()


@pytest.fixture
def app(db: AsyncSession) -> FastAPI:
    from app.main import create_app

    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
async def _dispose_engine() -> AsyncIterator[None]:
    yield
    await dispose_engine()
