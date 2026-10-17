"""M0: org units for the admin (UC-31). Process CRUD comes in M1 (docs/plan.md)."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import Conflict
from app.modules import audit
from app.modules.identity.deps import require_roles
from app.modules.identity.models import User, UserRole
from app.modules.org.models import OrgUnit

admin_router = APIRouter(prefix="/admin/org-units", tags=["admin"])
_admin = require_roles(UserRole.ADMIN)


class OrgUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class OrgUnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@admin_router.get("", response_model=list[OrgUnitOut])
async def list_org_units(_: User = Depends(_admin), db: AsyncSession = Depends(get_db)) -> list[OrgUnit]:
    return list((await db.execute(select(OrgUnit).order_by(OrgUnit.name))).scalars())


@admin_router.post("", response_model=OrgUnitOut, status_code=201)
async def create_org_unit(
    data: OrgUnitCreate, actor: User = Depends(_admin), db: AsyncSession = Depends(get_db)
) -> OrgUnit:
    name = data.name.strip()
    if (await db.execute(select(OrgUnit).where(OrgUnit.name == name))).scalar_one_or_none():
        raise Conflict("Подразделение с таким названием уже есть", code="org_unit_exists")
    unit = OrgUnit(name=name)
    db.add(unit)
    await db.flush()
    await audit.record(db, action="org_unit.created", entity="org_unit", entity_id=unit.id, user_id=actor.id)
    await db.commit()
    return unit
