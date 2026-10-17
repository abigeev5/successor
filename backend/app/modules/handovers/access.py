"""The single place that checks access to a handover (docs/architecture.md, 5.6)."""

import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import Forbidden, NotFound
from app.modules.handovers.domain.policy import HandoverFacts, HandoverRole, Viewer, resolve_role
from app.modules.handovers.models import Handover, HandoverMember
from app.modules.identity.deps import current_user
from app.modules.identity.models import User

NO_ACCESS = "Нет доступа к этой передаче дел"


@dataclass(frozen=True)
class HandoverAccess:
    handover_id: uuid.UUID
    user: User
    role: HandoverRole


async def get_handover_role(db: AsyncSession, user: User, handover_id: uuid.UUID) -> HandoverRole | None:
    handover = await db.get(Handover, handover_id)
    if handover is None:
        raise NotFound("Передача дел не найдена", code="handover_not_found")
    member_role = (
        await db.execute(
            select(HandoverMember.role).where(
                HandoverMember.handover_id == handover_id, HandoverMember.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    return resolve_role(
        Viewer(user_id=user.id, global_role=user.role.value, org_unit_id=user.org_unit_id),
        HandoverFacts(
            manager_id=handover.manager_id,
            org_unit_id=handover.org_unit_id,
            member_role=member_role.value if member_role else None,
        ),
    )


async def ensure_handover_access(
    db: AsyncSession, user: User, handover_id: uuid.UUID, allowed: Iterable[HandoverRole]
) -> HandoverAccess:
    role = await get_handover_role(db, user, handover_id)
    if role is None or role not in set(allowed):
        raise Forbidden(NO_ACCESS, code="handover_forbidden")
    return HandoverAccess(handover_id=handover_id, user=user, role=role)


def require_handover_access(*allowed: HandoverRole) -> Callable[..., Awaitable[HandoverAccess]]:
    """FastAPI dependency for routes with a `{handover_id}` path parameter."""

    async def dependency(
        handover_id: uuid.UUID,
        user: User = Depends(current_user),
        db: AsyncSession = Depends(get_db),
    ) -> HandoverAccess:
        return await ensure_handover_access(db, user, handover_id, allowed)

    return dependency
