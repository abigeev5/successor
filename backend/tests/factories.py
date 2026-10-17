"""Test data builders. Commit is left to the caller."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.modules.handovers.models import Handover, HandoverMember, HandoverReason, MemberRole
from app.modules.identity.models import User, UserRole
from app.modules.org.models import OrgUnit

PASSWORD = "password123"
_PASSWORD_HASH = hash_password(PASSWORD)


async def make_org_unit(db: AsyncSession, name: str | None = None) -> OrgUnit:
    unit = OrgUnit(name=name or f"Подразделение {uuid.uuid4().hex[:6]}")
    db.add(unit)
    await db.flush()
    return unit


async def make_user(
    db: AsyncSession,
    role: UserRole,
    *,
    org_unit: OrgUnit | None = None,
    email: str | None = None,
    is_active: bool = True,
) -> User:
    user = User(
        email=email or f"{role.value}-{uuid.uuid4().hex[:8]}@test.local",
        full_name=f"Тест {role.value}",
        role=role,
        password_hash=_PASSWORD_HASH,
        is_active=is_active,
        org_unit_id=org_unit.id if org_unit else None,
    )
    db.add(user)
    await db.flush()
    return user


async def make_handover(
    db: AsyncSession,
    *,
    org_unit: OrgUnit,
    manager: User,
    expert: User | None = None,
    successor: User | None = None,
) -> Handover:
    handover = Handover(org_unit_id=org_unit.id, manager_id=manager.id, reason=HandoverReason.RETIREMENT)
    db.add(handover)
    await db.flush()
    for user, role in ((expert, MemberRole.EXPERT), (successor, MemberRole.SUCCESSOR)):
        if user is not None:
            db.add(HandoverMember(handover_id=handover.id, user_id=user.id, role=role))
    await db.flush()
    return handover
