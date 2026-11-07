import uuid

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, NotFound, install_error_handlers
from app.modules.handovers.access import (
    HandoverAccess,
    HandoverRole,
    ensure_handover_access,
    require_handover_access,
)
from app.modules.identity.models import UserRole
from app.modules.identity.router import auth_router
from tests.factories import PASSWORD, make_handover, make_org_unit, make_user

ALL = list(HandoverRole)


async def test_roles_resolved_from_db(db: AsyncSession) -> None:
    unit, other_unit = await make_org_unit(db), await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    unit_manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    foreign_manager = await make_user(db, UserRole.MANAGER, org_unit=other_unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    other_expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    admin = await make_user(db, UserRole.ADMIN)
    handover = await make_handover(db, org_unit=unit, manager=manager, expert=expert, successor=successor)
    await db.commit()

    async def role_of(user):  # type: ignore[no-untyped-def]
        return (await ensure_handover_access(db, user, handover.id, ALL)).role

    assert await role_of(admin) is HandoverRole.ADMIN
    assert await role_of(manager) is HandoverRole.MANAGER
    assert await role_of(unit_manager) is HandoverRole.MANAGER
    assert await role_of(expert) is HandoverRole.EXPERT
    assert await role_of(successor) is HandoverRole.SUCCESSOR
    for outsider in (foreign_manager, other_expert):
        with pytest.raises(Forbidden):
            await ensure_handover_access(db, outsider, handover.id, ALL)


async def test_role_not_in_allowed_list_is_forbidden(db: AsyncSession) -> None:
    unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    handover = await make_handover(db, org_unit=unit, manager=manager, successor=successor)
    await db.commit()
    with pytest.raises(Forbidden, match="Нет доступа"):
        await ensure_handover_access(db, successor, handover.id, [HandoverRole.EXPERT, HandoverRole.MANAGER])


async def test_missing_handover_is_404(db: AsyncSession) -> None:
    admin = await make_user(db, UserRole.ADMIN)
    await db.commit()
    with pytest.raises(NotFound):
        await ensure_handover_access(db, admin, uuid.uuid4(), ALL)


async def test_dependency_returns_403_for_expert_of_other_handover(db: AsyncSession) -> None:
    unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit, email="expert@test.local")
    stranger = await make_user(db, UserRole.EXPERT, org_unit=unit, email="stranger@test.local")
    handover = await make_handover(db, org_unit=unit, manager=manager, expert=expert)
    await db.commit()

    app = FastAPI()
    install_error_handlers(app)
    app.include_router(auth_router, prefix="/api")

    @app.get("/api/handovers/{handover_id}/probe")
    async def probe(access: HandoverAccess = Depends(require_handover_access(HandoverRole.EXPERT))) -> str:
        return access.role.value

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/login", json={"email": "stranger@test.local", "password": PASSWORD})
        denied = await client.get(f"/api/handovers/{handover.id}/probe")
        assert denied.status_code == 403
        assert denied.json() == {"detail": "Нет доступа к этой передаче дел", "code": "handover_forbidden"}

        await client.post("/api/auth/login", json={"email": "expert@test.local", "password": PASSWORD})
        assert (await client.get(f"/api/handovers/{handover.id}/probe")).json() == "expert"
        assert stranger.id != expert.id
