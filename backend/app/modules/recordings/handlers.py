"""Uploaded → processed in the worker; recording steps as a knowledge source."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.core.events import EventBus
from app.modules.knowledge import resolvers
from app.modules.knowledge.domain.sources import SourceType
from app.modules.knowledge.resolvers import ResolvedSource
from app.modules.recordings.domain.steps import timecode
from app.modules.recordings.events import RecordingUploaded
from app.modules.recordings.models import Recording, RecordingStep
from app.modules.recordings.pipeline import process_recording

PROCESS_JOB = "process_recording"


class RecordingStepResolver:
    """A step opens the video at its start (SPEC 7.7); successors also see the video (SPEC 7.1)."""

    source_type = SourceType.RECORDING_STEP

    async def resolve(self, db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, ResolvedSource]:
        rows = await db.execute(
            select(RecordingStep, Recording)
            .join(Recording, Recording.id == RecordingStep.recording_id)
            .where(RecordingStep.id.in_(ids))
        )
        result = {}
        for step, recording in rows:
            context = step.action + (f"\nПочему так: {step.rationale}" if step.rationale else "")
            result[step.id] = ResolvedSource(
                label=f"Запись «{recording.title}», шаг {step.idx} · "
                f"{timecode(step.start_ms)}–{timecode(step.end_ms)}",
                context=context,
                link={
                    "recording_id": str(recording.id),
                    "video_asset_id": str(recording.video_asset_id),
                    "start_ms": str(step.start_ms),
                    "end_ms": str(step.end_ms),
                },
            )
        return result


def register(bus: EventBus) -> None:
    bus.subscribe_job(
        RecordingUploaded,
        PROCESS_JOB,
        dedup_key=lambda e: f"{PROCESS_JOB}:{e.recording_id}",
        payload=lambda e: {"recording_id": str(e.recording_id)},
    )
    jobs.register_handler(PROCESS_JOB, process_recording)
    resolvers.register(RecordingStepResolver())
