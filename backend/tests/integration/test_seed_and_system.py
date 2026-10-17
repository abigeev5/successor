import importlib.util
from pathlib import Path
from types import ModuleType

import httpx
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base, get_engine
from app.modules.identity.models import User

SEED_PATH = Path(__file__).resolve().parents[3] / "seed" / "seed.py"


def load_seed() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_script", SEED_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_seed_is_idempotent_and_demo_accounts_log_in(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    seed = load_seed()
    assert (await seed.seed(db))["users_created"] == 4
    assert (await seed.seed(db))["users_created"] == 0
    assert await db.scalar(select(func.count()).select_from(User)) == 4

    for email, role in [
        ("manager@demo.local", "manager"),
        ("expert@demo.local", "expert"),
        ("successor@demo.local", "successor"),
        ("admin@demo.local", "admin"),
    ]:
        response = await client.post("/api/auth/login", json={"email": email, "password": seed.DEMO_PASSWORD})
        assert response.status_code == 200, email
        assert response.json()["role"] == role


async def test_health_reports_db_and_fake_providers(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/health")).json()
    assert body["status"] == "ok"
    assert body["components"]["db"]["ok"] is True
    assert body["components"]["llm"] == {"ok": True, "provider": "fake", "detail": None}


async def test_meta(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/meta")).json()["demo_mode"] is True


async def test_migrations_match_models(db: AsyncSession) -> None:
    """Catches a model change without a migration (and broken migrations, see docs/lessons.md L-001)."""

    def diff(sync_conn):  # type: ignore[no-untyped-def]
        context = MigrationContext.configure(sync_conn, opts={"compare_type": True})
        return compare_metadata(context, Base.metadata)

    async with get_engine().connect() as conn:
        assert await conn.run_sync(diff) == []
