import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.modules.handovers.access import HandoverRole, ensure_handover_access
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.privacy import service

router = APIRouter(prefix="/consents", tags=["privacy"])
data_router = APIRouter(prefix="/privacy", tags=["privacy"])


class ConsentTextOut(BaseModel):
    version: str
    text: str
    hash: str


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    handover_id: uuid.UUID
    text_version: str
    accepted_at: datetime
    revoked_at: datetime | None


class ConsentIn(BaseModel):
    handover_id: uuid.UUID


@router.get("/current-text", response_model=ConsentTextOut)
async def current_text(
    _: User = Depends(current_user), settings: Settings = Depends(get_settings)
) -> ConsentTextOut:
    text = service.current_text(settings)
    return ConsentTextOut(version=text.version, text=text.text, hash=text.hash)


@router.get("/my", response_model=ConsentOut | None)
async def my_consent(
    handover_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> object:
    """The active consent of the current user for a handover, or null."""
    return await service.active_consent(db, user.id, handover_id)


@router.post("", response_model=ConsentOut, status_code=201)
async def accept(
    data: ConsentIn,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> object:
    await ensure_handover_access(db, user, data.handover_id, [HandoverRole.EXPERT])
    ip = request.client.host if request.client else None
    return await service.accept(db, settings, user_id=user.id, handover_id=data.handover_id, ip=ip)


@router.post("/{consent_id}/revoke", response_model=ConsentOut)
async def revoke(
    consent_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> object:
    return await service.revoke(db, consent_id=consent_id, user_id=user.id)


class MyDataOut(BaseModel):
    handover_id: uuid.UUID
    consent: ConsentOut | None
    counts: dict[str, int]  # interview_messages, recordings, gap_answers, files, files_bytes


class ErasedOut(BaseModel):
    counts: dict[str, int]
    files: int
    sources: int


@data_router.get("/my-data", response_model=MyDataOut)
async def my_data(
    handover_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> MyDataOut:
    consent, counts = await service.my_data(db, user, handover_id)
    return MyDataOut(
        handover_id=handover_id,
        consent=ConsentOut.model_validate(consent) if consent else None,
        counts=counts,
    )


@data_router.delete("/my-data", response_model=ErasedOut)
async def erase_my_data(
    handover_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ErasedOut:
    erased = await service.erase_my_data(db, settings, user, handover_id)
    return ErasedOut(counts=erased.counts, files=erased.files, sources=len(erased.sources))
