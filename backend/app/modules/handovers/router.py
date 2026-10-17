import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.modules.handovers import service
from app.modules.handovers.access import HandoverAccess, require_handover_access
from app.modules.handovers.domain.policy import HandoverRole
from app.modules.handovers.schemas import HandoverCreate, HandoverOut, HandoverUpdate
from app.modules.identity.deps import current_user, require_roles
from app.modules.identity.models import User, UserRole

router = APIRouter(prefix="/handovers", tags=["handovers"])


@router.get("", response_model=list[HandoverOut])
async def list_handovers(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[HandoverOut]:
    return await service.describe(db, await service.visible_handovers(db, user), user)


@router.post("", response_model=HandoverOut, status_code=201)
async def create_handover(
    data: HandoverCreate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
) -> HandoverOut:
    handover = await service.create_handover(db, data, user)
    return (await service.describe(db, [handover], user))[0]


@router.get("/{handover_id}", response_model=HandoverOut)
async def get_handover(
    access: HandoverAccess = Depends(require_handover_access(*HandoverRole)),
    db: AsyncSession = Depends(get_db),
) -> HandoverOut:
    handover = await service.get_handover(db, access.handover_id)
    return (await service.describe(db, [handover], access.user))[0]


@router.patch("/{handover_id}", response_model=HandoverOut)
async def update_handover(
    handover_id: uuid.UUID,
    data: HandoverUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> HandoverOut:
    handover = await service.update_handover(db, handover_id, data, user)
    return (await service.describe(db, [handover], user))[0]
