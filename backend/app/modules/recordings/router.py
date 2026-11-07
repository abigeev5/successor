import uuid

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.recordings import service
from app.modules.recordings.schemas import RecordingBrief, RecordingOut

router = APIRouter(prefix="/recordings", tags=["recordings"])


@router.post("", response_model=RecordingOut, status_code=201)
async def upload(
    video: UploadFile = File(...),
    handover_id: uuid.UUID = Form(...),
    title: str = Form(..., max_length=300),
    process_id: uuid.UUID | None = Form(None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RecordingOut:
    recording = await service.upload(
        db, settings, user, handover_id=handover_id, process_id=process_id, title=title, file=video.file
    )
    return await service.view(db, user, recording.id)


@router.get("", response_model=list[RecordingBrief])
async def list_recordings(
    handover_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[RecordingBrief]:
    return await service.list_recordings(db, user, handover_id)


@router.get("/{recording_id}", response_model=RecordingOut)
async def get_recording(
    recording_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> RecordingOut:
    return await service.view(db, user, recording_id)


@router.post("/{recording_id}/retry", response_model=RecordingOut)
async def retry(
    recording_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> RecordingOut:
    await service.retry(db, user, recording_id)
    return await service.view(db, user, recording_id)


@router.delete("/{recording_id}", status_code=204)
async def delete_recording(
    recording_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    await service.delete_recording(db, settings, user, recording_id)
    return Response(status_code=204)
