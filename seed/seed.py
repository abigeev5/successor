"""`make seed-demo`: loads fictional demo data. Idempotent: brings demo records to a known state.

Run from backend/ (the `app` package must be importable): `uv run python ../seed/seed.py`.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import dispose_engine, get_sessionmaker
from app.core.security import hash_password
from app.modules.identity.models import User, UserRole
from app.modules.org.models import OrgUnit

DATA = Path(__file__).resolve().parent / "data" / "demo.json"
DEMO_PASSWORD = "demo1234"


def load_data() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


async def seed(db: AsyncSession) -> dict[str, int]:
    data = load_data()

    unit = (await db.execute(select(OrgUnit).where(OrgUnit.name == data["org_unit"]))).scalar_one_or_none()
    if unit is None:
        unit = OrgUnit(name=data["org_unit"])
        db.add(unit)
        await db.flush()

    password_hash = hash_password(DEMO_PASSWORD)
    created = 0
    for raw in data["users"]:
        user = (await db.execute(select(User).where(User.email == raw["email"]))).scalar_one_or_none()
        if user is None:
            user = User(email=raw["email"])
            db.add(user)
            created += 1
        user.full_name = raw["full_name"]
        user.role = UserRole(raw["role"])
        user.password_hash = password_hash
        user.is_active = True
        user.org_unit_id = unit.id
    await db.commit()
    return {"users_created": created, "users_total": len(data["users"])}


async def main() -> None:
    async with get_sessionmaker()() as db:
        result = await seed(db)
    await dispose_engine()
    print(f"Демо-данные загружены: {result}. Пароль демо-учёток: {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
