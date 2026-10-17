import uuid
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, Forbidden, NotFound
from app.modules import audit
from app.modules.identity.models import User, UserRole
from app.modules.org.models import HolderLevel, Process, ProcessFrequency, ProcessHolder
from app.modules.org.schemas import HolderOut, ProcessOut

_LEVEL_STRENGTH = {HolderLevel.LEARNING: 0, HolderLevel.KNOWS: 1, HolderLevel.OWNER: 2}


def ensure_can_manage_unit(user: User, org_unit_id: uuid.UUID) -> None:
    if user.role is UserRole.ADMIN:
        return
    if user.role is UserRole.MANAGER and user.org_unit_id == org_unit_id:
        return
    raise Forbidden("Управлять процессами может руководитель подразделения")


def resolve_org_unit(user: User, requested: uuid.UUID | None) -> uuid.UUID:
    org_unit_id = requested or user.org_unit_id
    if org_unit_id is None:
        raise AppError("Укажите подразделение", code="org_unit_required")
    return org_unit_id


async def get_process(db: AsyncSession, process_id: uuid.UUID) -> Process:
    process = await db.get(Process, process_id)
    if process is None:
        raise NotFound("Процесс не найден", code="process_not_found")
    return process


async def get_processes(db: AsyncSession, ids: list[uuid.UUID]) -> list[Process]:
    if not ids:
        return []
    return list((await db.execute(select(Process).where(Process.id.in_(ids)))).scalars())


async def list_processes(db: AsyncSession, org_unit_id: uuid.UUID) -> list[Process]:
    stmt = (
        select(Process)
        .where(Process.org_unit_id == org_unit_id)
        .order_by(Process.criticality.desc(), Process.name)
    )
    return list((await db.execute(stmt)).scalars())


async def create_process(
    db: AsyncSession,
    *,
    org_unit_id: uuid.UUID,
    name: str,
    description: str = "",
    frequency: ProcessFrequency = ProcessFrequency.ADHOC,
    criticality: int = 2,
    created_by: uuid.UUID | None,
) -> Process:
    process = Process(
        org_unit_id=org_unit_id,
        name=name.strip(),
        description=description.strip(),
        frequency=frequency,
        criticality=criticality,
        created_by=created_by,
    )
    db.add(process)
    await db.flush()
    await audit.record(
        db, action="process.created", entity="process", entity_id=process.id, user_id=created_by
    )
    return process


async def set_holder(
    db: AsyncSession,
    process_id: uuid.UUID,
    user_id: uuid.UUID,
    level: HolderLevel,
    *,
    only_upgrade: bool = False,
) -> None:
    """Adds or changes who knows a process. With only_upgrade a stronger existing level is kept."""
    holder = await db.get(ProcessHolder, (process_id, user_id))
    if holder is None:
        db.add(ProcessHolder(process_id=process_id, user_id=user_id, level=level))
    elif not only_upgrade or _LEVEL_STRENGTH[level] > _LEVEL_STRENGTH[holder.level]:
        holder.level = level
    await db.flush()


async def remove_holder(db: AsyncSession, process_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await db.execute(
        delete(ProcessHolder).where(ProcessHolder.process_id == process_id, ProcessHolder.user_id == user_id)
    )


async def with_holders(db: AsyncSession, processes: list[Process]) -> list[ProcessOut]:
    ids = [p.id for p in processes]
    holders: dict[uuid.UUID, list[HolderOut]] = defaultdict(list)
    if ids:
        rows = await db.execute(
            select(ProcessHolder.process_id, ProcessHolder.user_id, User.full_name, ProcessHolder.level)
            .join(User, User.id == ProcessHolder.user_id)
            .where(ProcessHolder.process_id.in_(ids))
            .order_by(User.full_name)
        )
        for process_id, user_id, full_name, level in rows:
            holders[process_id].append(HolderOut(user_id=user_id, full_name=full_name, level=level))
    return [ProcessOut.model_validate(p).model_copy(update={"holders": holders[p.id]}) for p in processes]
