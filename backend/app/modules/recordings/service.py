"""Recordings use cases: upload, list, view, process again."""

import asyncio
import uuid
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.events import bus
from app.core.storage import Asset, AssetKind, store_stream
from app.modules import audit
from app.modules.handovers.access import HandoverRole, ensure_handover_access
from app.modules.handovers.service import list_processes
from app.modules.identity.models import User, UserRole
from app.modules.knowledge.domain.sources import SourceType
from app.modules.knowledge.models import CardSource, KnowledgeCard
from app.modules.privacy.erasure import sources_erased
from app.modules.privacy.service import require_consent
from app.modules.recordings.erasure import erase_recordings
from app.modules.recordings.events import RecordingUploaded
from app.modules.recordings.models import Recording, RecordingStatus, RecordingStep
from app.modules.recordings.schemas import RecordingBrief, RecordingOut, StepOut

UPLOADERS = [HandoverRole.EXPERT, HandoverRole.ADMIN]
VIEWERS = [HandoverRole.EXPERT, HandoverRole.MANAGER, HandoverRole.ADMIN]
NOT_FOUND = "Запись не найдена"
MB = 1024 * 1024


async def upload(
    db: AsyncSession,
    settings: Settings,
    user: User,
    *,
    handover_id: uuid.UUID,
    process_id: uuid.UUID | None,
    title: str,
    file: BinaryIO,
) -> Recording:
    access = await ensure_handover_access(db, user, handover_id, UPLOADERS)
    if access.role is HandoverRole.EXPERT:
        await require_consent(db, user.id, handover_id)
    title = title.strip()
    if not title:
        raise AppError(
            "Назовите запись: например, «Оформление направления на пересдачу»", code="title_required"
        )
    if process_id is not None and process_id not in {p.id for p in await list_processes(db, handover_id)}:
        raise AppError("Процесс не входит в эту передачу дел", code="bad_process")
    asset = await asyncio.to_thread(
        store_stream,
        settings,
        file,
        expected_kind=AssetKind.VIDEO,
        max_bytes=settings.recording_max_mb * MB,
        owner_id=user.id,
        handover_id=handover_id,
    )
    db.add(asset)
    recording = Recording(
        handover_id=handover_id,
        process_id=process_id,
        video_asset_id=asset.id,
        title=title[:300],
        created_by=user.id,
    )
    db.add(recording)
    await db.flush()
    await bus.publish(
        db,
        RecordingUploaded(
            recording_id=recording.id, handover_id=handover_id, user_id=user.id, size_bytes=asset.size_bytes
        ),
    )
    await audit.record(
        db, action="recording.uploaded", entity="recording", entity_id=recording.id, user_id=user.id
    )
    await db.commit()
    return recording


async def _load(
    db: AsyncSession, user: User, recording_id: uuid.UUID, allowed: list[HandoverRole]
) -> Recording:
    recording = await db.get(Recording, recording_id)
    if recording is None:
        raise NotFound(NOT_FOUND, code="recording_not_found")
    await ensure_handover_access(db, user, recording.handover_id, allowed)
    return recording


async def delete_recording(db: AsyncSession, settings: Settings, user: User, recording_id: uuid.UUID) -> None:
    """`DELETE /recordings/{id}`: the expert deletes their own recording; admin — any."""
    recording = await _load(db, user, recording_id, UPLOADERS)
    if user.role is not UserRole.ADMIN and recording.created_by != user.id:
        raise Forbidden("Удалить запись может только тот, кто её сделал", code="recording_forbidden")
    if recording.status is RecordingStatus.PROCESSING:
        raise Conflict(
            "Запись ещё обрабатывается. Удалите её, когда обработка закончится.", code="recording_busy"
        )
    handover_id = recording.handover_id
    erased = await erase_recordings(db, settings, [recording])
    await sources_erased(db, handover_id=handover_id, user_id=user.id, sources=erased.sources)
    await audit.record(
        db,
        action="recording.deleted",
        entity="recording",
        entity_id=recording_id,
        user_id=user.id,
        meta={"handover_id": str(handover_id), "files": erased.files},
    )
    await db.commit()


async def retry(db: AsyncSession, user: User, recording_id: uuid.UUID) -> Recording:
    recording = await _load(db, user, recording_id, UPLOADERS)
    if recording.status is not RecordingStatus.FAILED:
        raise Conflict("Запись уже обработана или обрабатывается", code="recording_not_failed")
    recording.status = RecordingStatus.UPLOADED
    recording.error = None
    await bus.publish(
        db,
        RecordingUploaded(
            recording_id=recording.id, handover_id=recording.handover_id, user_id=user.id, size_bytes=0
        ),
    )
    await db.commit()
    return recording


def _brief(r: Recording) -> RecordingBrief:
    return RecordingBrief(
        id=r.id,
        handover_id=r.handover_id,
        process_id=r.process_id,
        title=r.title,
        status=r.status,
        stage=r.stage,
        error=r.error,
        duration_ms=r.duration_ms,
        created_at=r.created_at,
    )


async def list_recordings(db: AsyncSession, user: User, handover_id: uuid.UUID) -> list[RecordingBrief]:
    await ensure_handover_access(db, user, handover_id, VIEWERS)
    rows = (
        await db.execute(
            select(Recording)
            .where(Recording.handover_id == handover_id)
            .order_by(Recording.created_at.desc())
        )
    ).scalars()
    return [_brief(r) for r in rows]


async def view(db: AsyncSession, user: User, recording_id: uuid.UUID) -> RecordingOut:
    recording = await _load(db, user, recording_id, VIEWERS)
    steps = list(
        (
            await db.execute(
                select(RecordingStep)
                .where(RecordingStep.recording_id == recording.id)
                .order_by(RecordingStep.idx)
            )
        ).scalars()
    )
    card = None
    if steps:
        card = (
            await db.execute(
                select(KnowledgeCard)
                .join(CardSource, CardSource.card_id == KnowledgeCard.id)
                .where(
                    CardSource.source_type == SourceType.RECORDING_STEP,
                    CardSource.source_id.in_([s.id for s in steps]),
                )
                .order_by(KnowledgeCard.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    video = await db.get(Asset, recording.video_asset_id)
    return RecordingOut(
        **_brief(recording).model_dump(),
        video_asset_id=recording.video_asset_id,
        video_available=video is not None and video.deleted_at is None,
        steps=[
            StepOut(
                id=s.id,
                idx=s.idx,
                title=s.title,
                action=s.action,
                rationale=s.rationale,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                screenshot_asset_id=s.screenshot_asset_id,
                screenshot_blurred=s.screenshot_blurred,
            )
            for s in steps
        ],
        card_id=card.id if card else None,
        card_status=card.status.value if card else None,
    )
