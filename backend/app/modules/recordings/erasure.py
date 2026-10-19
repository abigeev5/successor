"""Deleting screen recordings: video, screenshots, transcript and steps are removed for good."""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.storage import Asset, erase_file
from app.modules.knowledge.domain.sources import SourceType
from app.modules.privacy.erasure import Erased, ErasedSource
from app.modules.recordings.models import Recording, RecordingStep, SegmentSource, TranscriptSegment


async def erase_recordings(db: AsyncSession, settings: Settings, recordings: list[Recording]) -> Erased:
    """No commit. Cards made from the steps are handled by knowledge (privacy.sources_erased)."""
    ids = [r.id for r in recordings]
    if not ids:
        return Erased(counts={"recordings": 0})
    steps = (
        await db.execute(
            select(RecordingStep.id, RecordingStep.screenshot_asset_id).where(
                RecordingStep.recording_id.in_(ids)
            )
        )
    ).all()
    segments = list(
        (
            await db.execute(
                select(TranscriptSegment.id).where(
                    TranscriptSegment.source_type == SegmentSource.RECORDING,
                    TranscriptSegment.source_id.in_(ids),
                )
            )
        ).scalars()
    )
    asset_ids = [r.video_asset_id for r in recordings] + [a for _, a in steps if a is not None]
    files = 0
    for asset in (await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))).scalars():
        if erase_file(settings, asset):
            files += 1
    await db.execute(delete(TranscriptSegment).where(TranscriptSegment.id.in_(segments)))
    await db.execute(delete(Recording).where(Recording.id.in_(ids)))  # steps: ON DELETE CASCADE
    return Erased(
        counts={"recordings": len(ids)},
        sources=[ErasedSource(SourceType.RECORDING_STEP.value, step_id) for step_id, _ in steps]
        + [ErasedSource(SourceType.TRANSCRIPT_SEGMENT.value, segment_id) for segment_id in segments],
        files=files,
    )


class RecordingsEraser:
    async def describe(
        self, db: AsyncSession, *, user_id: uuid.UUID, handover_id: uuid.UUID
    ) -> dict[str, int]:
        count = await db.scalar(
            select(func.count())
            .select_from(Recording)
            .where(Recording.handover_id == handover_id, Recording.created_by == user_id)
        )
        return {"recordings": count or 0}

    async def erase(
        self, db: AsyncSession, settings: Settings, *, user_id: uuid.UUID, handover_id: uuid.UUID
    ) -> Erased:
        recordings = list(
            (
                await db.execute(
                    select(Recording).where(
                        Recording.handover_id == handover_id, Recording.created_by == user_id
                    )
                )
            ).scalars()
        )
        return await erase_recordings(db, settings, recordings)
