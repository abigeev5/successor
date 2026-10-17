import uuid
from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFound
from app.modules import audit
from app.modules.handovers.access import ensure_handover_access, get_handover_role
from app.modules.handovers.domain.policy import HandoverRole
from app.modules.handovers.models import Handover, HandoverMember, HandoverProcess, HandoverStatus, MemberRole
from app.modules.handovers.schemas import HandoverCreate, HandoverOut, HandoverUpdate, ProcessBrief
from app.modules.identity.models import User, UserRole
from app.modules.identity.schemas import UserBrief
from app.modules.org import service as org
from app.modules.org.models import HolderLevel, OrgUnit, Process

MANAGERS = (HandoverRole.ADMIN, HandoverRole.MANAGER)


async def get_handover(db: AsyncSession, handover_id: uuid.UUID) -> Handover:
    handover = await db.get(Handover, handover_id)
    if handover is None:
        raise NotFound("Передача дел не найдена", code="handover_not_found")
    return handover


async def member_ids(db: AsyncSession, handover_id: uuid.UUID, role: MemberRole) -> list[uuid.UUID]:
    stmt = select(HandoverMember.user_id).where(
        HandoverMember.handover_id == handover_id, HandoverMember.role == role
    )
    return list((await db.execute(stmt)).scalars())


async def list_processes(db: AsyncSession, handover_id: uuid.UUID) -> list[Process]:
    stmt = (
        select(Process)
        .join(HandoverProcess, HandoverProcess.process_id == Process.id)
        .where(HandoverProcess.handover_id == handover_id)
        .order_by(Process.criticality.desc(), Process.name)
    )
    return list((await db.execute(stmt)).scalars())


async def link_processes(db: AsyncSession, handover: Handover, process_ids: list[uuid.UUID]) -> None:
    """Links processes to the handover; experts become owners, successors learners (SPEC 7.2)."""
    processes = await org.get_processes(db, process_ids)
    if len(processes) != len(set(process_ids)) or any(
        p.org_unit_id != handover.org_unit_id for p in processes
    ):
        raise AppError("Процессы должны принадлежать подразделению передачи дел", code="bad_processes")
    linked = set(
        (
            await db.execute(
                select(HandoverProcess.process_id).where(HandoverProcess.handover_id == handover.id)
            )
        )
        .scalars()
        .all()
    )
    experts = await member_ids(db, handover.id, MemberRole.EXPERT)
    successors = await member_ids(db, handover.id, MemberRole.SUCCESSOR)
    for process in processes:
        if process.id not in linked:
            db.add(HandoverProcess(handover_id=handover.id, process_id=process.id))
        for user_id in experts:
            await org.set_holder(db, process.id, user_id, HolderLevel.OWNER, only_upgrade=True)
        for user_id in successors:
            await org.set_holder(db, process.id, user_id, HolderLevel.LEARNING, only_upgrade=True)
    await db.flush()


async def _active_user(db: AsyncSession, user_id: uuid.UUID, what: str) -> User:
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(f"{what} не найден", code="user_not_found")
    return user


async def create_handover(db: AsyncSession, data: HandoverCreate, actor: User) -> Handover:
    org_unit_id = org.resolve_org_unit(actor, data.org_unit_id)
    org.ensure_can_manage_unit(actor, org_unit_id)
    expert = await _active_user(db, data.expert_id, "Эксперт")
    handover = Handover(
        org_unit_id=org_unit_id,
        manager_id=actor.id,
        reason=data.reason,
        deadline=data.deadline,
        status=HandoverStatus.ACTIVE,
    )
    db.add(handover)
    await db.flush()
    db.add(HandoverMember(handover_id=handover.id, user_id=expert.id, role=MemberRole.EXPERT))
    if data.successor_id:
        successor = await _active_user(db, data.successor_id, "Преемник")
        db.add(HandoverMember(handover_id=handover.id, user_id=successor.id, role=MemberRole.SUCCESSOR))
    await db.flush()
    await link_processes(db, handover, data.process_ids)
    await audit.record(
        db, action="handover.created", entity="handover", entity_id=handover.id, user_id=actor.id
    )
    await db.commit()
    return handover


async def update_handover(
    db: AsyncSession, handover_id: uuid.UUID, data: HandoverUpdate, actor: User
) -> Handover:
    await ensure_handover_access(db, actor, handover_id, MANAGERS)
    handover = await get_handover(db, handover_id)
    changes = data.model_dump(exclude_unset=True)
    for field in ("reason", "deadline", "status"):
        if field in changes:
            setattr(handover, field, changes[field])
    if "successor_id" in changes:
        current = await member_ids(db, handover.id, MemberRole.SUCCESSOR)
        for user_id in current:
            await db.delete(await db.get(HandoverMember, (handover.id, user_id)))
        await db.flush()
        if data.successor_id:
            await _active_user(db, data.successor_id, "Преемник")
            db.add(
                HandoverMember(handover_id=handover.id, user_id=data.successor_id, role=MemberRole.SUCCESSOR)
            )
            await db.flush()
    if data.process_ids is not None:
        await link_processes(db, handover, data.process_ids)
    await audit.record(
        db,
        action="handover.updated",
        entity="handover",
        entity_id=handover.id,
        user_id=actor.id,
        meta={"fields": sorted(changes)},
    )
    await db.commit()
    return handover


async def visible_handovers(db: AsyncSession, user: User) -> list[Handover]:
    stmt = select(Handover).order_by(Handover.created_at.desc())
    if user.role is UserRole.ADMIN:
        pass
    elif user.role is UserRole.MANAGER:
        conditions = [Handover.manager_id == user.id]
        if user.org_unit_id:
            conditions.append(Handover.org_unit_id == user.org_unit_id)
        stmt = stmt.where(or_(*conditions))
    else:
        stmt = stmt.join(HandoverMember, HandoverMember.handover_id == Handover.id).where(
            HandoverMember.user_id == user.id
        )
    return list((await db.execute(stmt)).scalars().unique())


async def describe(db: AsyncSession, handovers: list[Handover], viewer: User) -> list[HandoverOut]:
    """Builds API views with people and processes in a few queries."""
    if not handovers:
        return []
    ids = [h.id for h in handovers]
    units = {u.id: u.name for u in (await db.execute(select(OrgUnit))).scalars()}
    members = await db.execute(
        select(HandoverMember.handover_id, HandoverMember.role, User)
        .join(User, User.id == HandoverMember.user_id)
        .where(HandoverMember.handover_id.in_(ids))
        .order_by(User.full_name)
    )
    people: dict[tuple[uuid.UUID, MemberRole], list[UserBrief]] = defaultdict(list)
    for handover_id, role, user in members:
        people[(handover_id, role)].append(UserBrief.model_validate(user))
    managers = {
        u.id: UserBrief.model_validate(u)
        for u in (
            await db.execute(select(User).where(User.id.in_({h.manager_id for h in handovers})))
        ).scalars()
    }
    links = await db.execute(
        select(HandoverProcess.handover_id, Process)
        .join(Process, Process.id == HandoverProcess.process_id)
        .where(HandoverProcess.handover_id.in_(ids))
        .order_by(Process.criticality.desc(), Process.name)
    )
    processes: dict[uuid.UUID, list[ProcessBrief]] = defaultdict(list)
    for handover_id, process in links:
        processes[handover_id].append(
            ProcessBrief(
                id=process.id, name=process.name, criticality=process.criticality, frequency=process.frequency
            )
        )
    return [
        HandoverOut(
            id=h.id,
            org_unit_id=h.org_unit_id,
            org_unit_name=units.get(h.org_unit_id, ""),
            manager=managers[h.manager_id],
            experts=people[(h.id, MemberRole.EXPERT)],
            successors=people[(h.id, MemberRole.SUCCESSOR)],
            reason=h.reason,
            deadline=h.deadline,
            status=h.status,
            processes=processes[h.id],
            created_at=h.created_at,
            my_role=await get_handover_role(db, viewer, h.id),
        )
        for h in handovers
    ]
