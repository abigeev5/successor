import uuid

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.modules.handovers.access import HandoverRole, ensure_handover_access
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.modules.interview import service
from app.modules.interview.schemas import (
    AudioOut,
    ConfirmIn,
    ProcessCoverageOut,
    SessionBrief,
    SessionOut,
    StartIn,
    TurnIn,
)
from app.providers.registry import Providers

router = APIRouter(prefix="/interviews", tags=["interviews"])


def providers(request: Request) -> Providers:
    return request.app.state.providers  # type: ignore[no-any-return]


@router.get("", response_model=list[SessionBrief])
async def list_sessions(
    handover_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[SessionBrief]:
    await ensure_handover_access(db, user, handover_id, list(HandoverRole))
    return await service.list_sessions(db, handover_id)


@router.get("/coverage", response_model=list[ProcessCoverageOut])
async def coverage(
    handover_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[ProcessCoverageOut]:
    await ensure_handover_access(db, user, handover_id, list(HandoverRole))
    return await service.handover_coverage(db, handover_id)


@router.post("", response_model=SessionOut, status_code=201)
async def start(
    data: StartIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    p: Providers = Depends(providers),
) -> SessionOut:
    session = await service.start(db, p, user, data.handover_id)
    return await service.session_view(db, user, session.id)


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> SessionOut:
    return await service.session_view(db, user, session_id)


@router.post("/{session_id}/messages", response_model=SessionOut)
async def post_message(
    session_id: uuid.UUID,
    data: TurnIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    p: Providers = Depends(providers),
) -> SessionOut:
    await service.post_message(db, p, user, session_id, data.text, data.audio_asset_id)
    return await service.session_view(db, user, session_id)


@router.post("/{session_id}/audio", response_model=AudioOut)
async def audio(
    session_id: uuid.UUID,
    file: UploadFile,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    p: Providers = Depends(providers),
) -> AudioOut:
    data = await file.read(service.MAX_AUDIO_BYTES + 1)
    return await service.transcribe_audio(db, settings, p, user, session_id, data)


@router.post("/{session_id}/confirm-processes", response_model=SessionOut)
async def confirm_processes(
    session_id: uuid.UUID,
    data: ConfirmIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    p: Providers = Depends(providers),
) -> SessionOut:
    await service.confirm_processes(db, p, user, session_id, data.items)
    return await service.session_view(db, user, session_id)


@router.post("/{session_id}/next-process", response_model=SessionOut)
async def next_process(
    session_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    p: Providers = Depends(providers),
) -> SessionOut:
    await service.next_process(db, p, user, session_id)
    return await service.session_view(db, user, session_id)


@router.post("/{session_id}/pause", response_model=SessionOut)
async def pause(
    session_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> SessionOut:
    await service.set_paused(db, user, session_id, paused=True)
    return await service.session_view(db, user, session_id)


@router.post("/{session_id}/resume", response_model=SessionOut)
async def resume(
    session_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> SessionOut:
    await service.set_paused(db, user, session_id, paused=False)
    return await service.session_view(db, user, session_id)


@router.post("/{session_id}/finish", response_model=SessionOut)
async def finish(
    session_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> SessionOut:
    await service.finish(db, user, session_id)
    return await service.session_view(db, user, session_id)
