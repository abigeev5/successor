import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import Conflict
from app.modules import audit
from app.modules.identity.deps import require_roles
from app.modules.identity.models import User, UserRole
from app.modules.org import service
from app.modules.org.models import OrgUnit
from app.modules.org.schemas import HolderSet, ProcessCreate, ProcessOut, ProcessUpdate

admin_router = APIRouter(prefix="/admin/org-units", tags=["admin"])
processes_router = APIRouter(prefix="/processes", tags=["processes"])
_admin = require_roles(UserRole.ADMIN)
_manager = require_roles(UserRole.ADMIN, UserRole.MANAGER)


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


@processes_router.get("", response_model=list[ProcessOut])
async def list_processes(
    org_unit_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> list[ProcessOut]:
    unit_id = service.resolve_org_unit(user, org_unit_id)
    service.ensure_can_manage_unit(user, unit_id)
    return await service.with_holders(db, await service.list_processes(db, unit_id))


@processes_router.post("", response_model=ProcessOut, status_code=201)
async def create_process(
    data: ProcessCreate, user: User = Depends(_manager), db: AsyncSession = Depends(get_db)
) -> ProcessOut:
    unit_id = service.resolve_org_unit(user, data.org_unit_id)
    service.ensure_can_manage_unit(user, unit_id)
    process = await service.create_process(
        db,
        org_unit_id=unit_id,
        name=data.name,
        description=data.description,
        frequency=data.frequency,
        criticality=data.criticality,
        created_by=user.id,
    )
    await db.commit()
    return (await service.with_holders(db, [process]))[0]


@processes_router.patch("/{process_id}", response_model=ProcessOut)
async def update_process(
    process_id: uuid.UUID,
    data: ProcessUpdate,
    user: User = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> ProcessOut:
    process = await service.get_process(db, process_id)
    service.ensure_can_manage_unit(user, process.org_unit_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(process, field, value)
    await audit.record(db, action="process.updated", entity="process", entity_id=process.id, user_id=user.id)
    await db.commit()
    return (await service.with_holders(db, [process]))[0]


@processes_router.post("/{process_id}/holders", response_model=ProcessOut)
async def set_holder(
    process_id: uuid.UUID, data: HolderSet, user: User = Depends(_manager), db: AsyncSession = Depends(get_db)
) -> ProcessOut:
    process = await service.get_process(db, process_id)
    service.ensure_can_manage_unit(user, process.org_unit_id)
    await service.set_holder(db, process_id, data.user_id, data.level)
    await db.commit()
    return (await service.with_holders(db, [process]))[0]


@processes_router.delete("/{process_id}/holders/{user_id}", response_model=ProcessOut)
async def remove_holder(
    process_id: uuid.UUID,
    user_id: uuid.UUID,
    user: User = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> ProcessOut:
    process = await service.get_process(db, process_id)
    service.ensure_can_manage_unit(user, process.org_unit_id)
    await service.remove_holder(db, process_id, user_id)
    await db.commit()
    return (await service.with_holders(db, [process]))[0]
