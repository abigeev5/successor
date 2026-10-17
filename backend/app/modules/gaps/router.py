import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.modules.gaps import service
from app.modules.gaps.models import GapStatus
from app.modules.gaps.schemas import GapAnswerIn, GapAssignIn, GapCreate, GapOut
from app.modules.identity.deps import current_user
from app.modules.identity.models import User

router = APIRouter(prefix="/gaps", tags=["gaps"])


@router.get("", response_model=list[GapOut])
async def list_gaps(
    handover_id: uuid.UUID,
    status: GapStatus | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GapOut]:
    return await service.list_gaps(db, user, handover_id, status)


@router.post("", response_model=GapOut, status_code=201)
async def create(
    data: GapCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> GapOut:
    gap = await service.create_manual(db, user, data.handover_id, data.question, data.qa_log_id)
    return await service.gap_view(db, user, gap.id)


@router.post("/{gap_id}/answer", response_model=GapOut)
async def answer(
    gap_id: uuid.UUID,
    data: GapAnswerIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> GapOut:
    await service.answer(db, user, gap_id, data.text)
    return await service.gap_view(db, user, gap_id)


@router.post("/{gap_id}/dismiss", response_model=GapOut)
async def dismiss(
    gap_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> GapOut:
    await service.dismiss(db, user, gap_id)
    return await service.gap_view(db, user, gap_id)


@router.patch("/{gap_id}", response_model=GapOut)
async def reassign(
    gap_id: uuid.UUID,
    data: GapAssignIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> GapOut:
    await service.reassign(db, user, gap_id, data.assignee_id)
    return await service.gap_view(db, user, gap_id)
