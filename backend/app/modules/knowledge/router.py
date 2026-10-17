import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.modules.handovers.access import HandoverRole, ensure_handover_access
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.knowledge import service
from app.modules.knowledge.domain.card_types import CardType
from app.modules.knowledge.models import CardStatus, KnowledgeCard
from app.modules.knowledge.schemas import (
    ApproveIn,
    CardCreate,
    CardDetail,
    CardEdit,
    CardListItem,
    MergeIn,
    RejectIn,
)

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("", response_model=list[CardListItem])
async def list_cards(
    handover_id: uuid.UUID,
    status: CardStatus | None = None,
    process_id: uuid.UUID | None = None,
    type: CardType | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeCard]:
    access = await ensure_handover_access(db, user, handover_id, service.READERS)
    return await service.list_cards(db, access, status=status, process_id=process_id, card_type=type)


@router.get("/{card_id}", response_model=CardDetail)
async def get_card(
    card_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> CardDetail:
    card, access = await service.load_card(db, user, card_id, service.READERS)
    return await service.card_detail(db, card, access.role)


async def _reviewed(db: AsyncSession, user: User, card_id: uuid.UUID) -> KnowledgeCard:
    card, _ = await service.load_card(db, user, card_id, service.REVIEWERS)
    return card


@router.patch("/{card_id}", response_model=CardDetail)
async def edit_card(
    card_id: uuid.UUID, data: CardEdit, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> CardDetail:
    card = await service.edit_card(db, await _reviewed(db, user, card_id), data, user)
    return await service.card_detail(db, card, HandoverRole.EXPERT)


@router.post("/{card_id}/approve", response_model=CardDetail)
async def approve(
    card_id: uuid.UUID,
    data: ApproveIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> CardDetail:
    card = await service.approve(
        db, await _reviewed(db, user, card_id), user, data.edits, data.review_seconds
    )
    return await service.card_detail(db, card, HandoverRole.EXPERT)


@router.post("/{card_id}/reject", response_model=CardDetail)
async def reject(
    card_id: uuid.UUID, data: RejectIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> CardDetail:
    card = await service.reject(
        db, await _reviewed(db, user, card_id), user, data.reason, data.review_seconds
    )
    return await service.card_detail(db, card, HandoverRole.EXPERT)


@router.post("/{card_id}/merge", response_model=CardDetail)
async def merge(
    card_id: uuid.UUID, data: MergeIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> CardDetail:
    card = await service.merge(db, await _reviewed(db, user, card_id), data.into_card_id, user)
    return await service.card_detail(db, card, HandoverRole.EXPERT)


@router.post("", response_model=CardDetail, status_code=201)
async def create_card(
    data: CardCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> CardDetail:
    card = await service.create_manual(db, data, user)
    return await service.card_detail(db, card, HandoverRole.EXPERT)
