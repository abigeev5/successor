"""Job `process_recording`: audio → speech → steps → screenshots with personal data blurred
→ a `procedure` draft. The page polls the recording's status and stage.
"""

import asyncio
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.events import bus
from app.core.jobs import JobContext
from app.core.prompts import get_prompts
from app.core.storage import Asset, AssetKind, absolute_path, save_bytes
from app.modules.knowledge.domain.card_types import CardType
from app.modules.knowledge.domain.sources import CardOrigin, SourceType
from app.modules.knowledge.models import KnowledgeCard
from app.modules.knowledge.service import DraftSource, create_draft
from app.modules.recordings import media
from app.modules.recordings.blur import blur_regions
from app.modules.recordings.domain.pii import find_pii
from app.modules.recordings.domain.steps import StepDraft, fix_steps, frame_at, procedure_markdown
from app.modules.recordings.events import RecordingProcessed
from app.modules.recordings.models import (
    Recording,
    RecordingStage,
    RecordingStatus,
    RecordingStep,
    SegmentSource,
    TranscriptSegment,
)
from app.modules.recordings.ner import find_persons
from app.providers.asr.base import Segment
from app.providers.llm.base import LLMError, Message
from app.providers.registry import Providers

log = logging.getLogger(__name__)
SEGMENT_PROMPT = "segment_recording"
MAX_SCREENSHOT_BYTES = 20 * 1024 * 1024
NO_SOUND = "В записи нет звука. Включите микрофон и комментируйте вслух: шаги выделяются по вашим словам."
GENERIC_ERROR = (
    "Не удалось обработать запись. Нажмите «Обработать заново»; если не поможет — сообщите администратору."
)


class RecordingFailed(Exception):
    """The message is shown to the expert."""


class StepIn(BaseModel):
    idx: int = 0
    title: str
    action: str = ""
    rationale: str | None = None
    start_ms: int
    end_ms: int


class StepsOut(BaseModel):
    steps: list[StepIn] = Field(default_factory=list)


async def _stage(db: AsyncSession, recording: Recording, stage: RecordingStage) -> None:
    recording.status = RecordingStatus.PROCESSING
    recording.stage = stage
    await db.commit()


async def _recognize(
    providers: Providers, settings: Settings, recording: Recording, video: Path
) -> list[Segment]:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        try:
            if not await asyncio.to_thread(media.has_audio, video):
                raise RecordingFailed(NO_SOUND)
            duration = await asyncio.to_thread(media.extract_audio, video, wav)
        except media.MediaError as exc:
            raise RecordingFailed(str(exc)) from exc
        if duration > settings.recording_max_minutes * 60_000:
            raise RecordingFailed(
                f"Запись длиннее {settings.recording_max_minutes} минут. Разбейте её на части."
            )
        recording.duration_ms = duration
        try:
            transcript = await asyncio.to_thread(providers.asr.transcribe, wav, "ru")
        except Exception as exc:
            log.warning("ASR failed for recording %s: %s", recording.id, exc)
            raise RecordingFailed(
                "Не удалось распознать речь. Проверьте, что распознавание речи настроено."
            ) from exc
    segments = [s for s in transcript.segments if s.text.strip()]
    if not segments:
        raise RecordingFailed("В записи не распознана речь. Комментируйте вслух, что и зачем делаете.")
    return segments


async def _segment(providers: Providers, segments: list[Segment], duration_ms: int) -> list[StepDraft]:
    prompt = get_prompts().render(
        SEGMENT_PROMPT,
        segments=[{"start_ms": s.start_ms, "end_ms": s.end_ms, "text": s.text.strip()} for s in segments],
    )
    try:
        out = await providers.llm.complete_json([Message("user", prompt.text)], StepsOut)
    except LLMError as exc:
        log.warning("segment_recording failed: %s", exc)
        raise RecordingFailed(
            "Модель не смогла разбить запись на шаги. Попробуйте обработать запись заново."
        ) from exc
    steps = fix_steps(
        [StepDraft(s.title, s.action, s.rationale, s.start_ms, s.end_ms) for s in out.steps], duration_ms
    )
    if not steps:
        raise RecordingFailed("Не удалось выделить шаги. Возможно, в записи слишком мало комментариев.")
    return steps


async def _screenshot(
    db: AsyncSession,
    providers: Providers,
    settings: Settings,
    recording: Recording,
    video: Path,
    step: StepDraft,
) -> tuple[Asset | None, bool]:
    """A frame with personal data blurred.

    If OCR fails, there is no screenshot: frames not checked for personal data are not kept.
    """
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "frame.png"
        try:
            await asyncio.to_thread(media.grab_frame, video, frame_at(step), png)
            boxes = await asyncio.to_thread(providers.ocr.read, png)
        except Exception as exc:
            log.warning("screenshot skipped for recording %s: %s", recording.id, exc)
            return None, False
        hits = await asyncio.to_thread(find_pii, boxes, find_persons)
        rects = [(boxes[i].x, boxes[i].y, boxes[i].width, boxes[i].height) for h in hits for i in h.boxes]
        if rects:
            await asyncio.to_thread(blur_regions, png, rects)
        asset = await save_bytes(
            db,
            settings,
            png.read_bytes(),
            expected_kind=AssetKind.IMAGE,
            max_bytes=MAX_SCREENSHOT_BYTES,
            owner_id=recording.created_by,
            handover_id=recording.handover_id,
        )
    return asset, bool(rects)


async def save_segments(db: AsyncSession, recording_id: uuid.UUID, segments: list[Segment]) -> None:
    await db.execute(
        delete(TranscriptSegment).where(
            TranscriptSegment.source_type == SegmentSource.RECORDING,
            TranscriptSegment.source_id == recording_id,
        )
    )
    for s in segments:
        db.add(
            TranscriptSegment(
                source_type=SegmentSource.RECORDING,
                source_id=recording_id,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                text=s.text.strip(),
            )
        )


async def build_steps(
    db: AsyncSession,
    providers: Providers,
    settings: Settings,
    recording: Recording,
    video: Path,
    steps: list[StepDraft],
) -> KnowledgeCard:
    """Screenshots, steps and the procedure draft; the recording becomes ready. Also used by the seed."""
    await db.execute(delete(RecordingStep).where(RecordingStep.recording_id == recording.id))
    rows: list[RecordingStep] = []
    urls: list[str | None] = []
    for n, step in enumerate(steps, start=1):
        asset, blurred = await _screenshot(db, providers, settings, recording, video, step)
        row = RecordingStep(
            recording_id=recording.id,
            idx=n,
            title=step.title,
            action=step.action,
            rationale=step.rationale,
            start_ms=step.start_ms,
            end_ms=step.end_ms,
            screenshot_asset_id=asset.id if asset else None,
            screenshot_blurred=blurred,
        )
        db.add(row)
        rows.append(row)
        urls.append(f"/api/assets/{asset.id}" if asset else None)
    await db.flush()
    card = await create_draft(
        db,
        handover_id=recording.handover_id,
        process_id=recording.process_id,
        card_type=CardType.PROCEDURE,
        title=recording.title,
        summary=f"Пошаговая инструкция по записи экрана «{recording.title}».",
        body_md=procedure_markdown(steps, urls),
        origin=CardOrigin.RECORDING,
        sources=[
            DraftSource(SourceType.RECORDING_STEP, row.id, row.action or row.title, row.start_ms, row.end_ms)
            for row in rows
        ],
        created_by=recording.created_by,
    )
    recording.status = RecordingStatus.READY
    recording.stage = None
    recording.error = None
    await bus.publish(
        db,
        RecordingProcessed(
            recording_id=recording.id,
            handover_id=recording.handover_id,
            duration_ms=recording.duration_ms or 0,
            steps=len(rows),
            blurred_screenshots=sum(r.screenshot_blurred for r in rows),
        ),
    )
    await db.commit()
    return card


async def _process(db: AsyncSession, providers: Providers, settings: Settings, recording: Recording) -> None:
    asset = await db.get(Asset, recording.video_asset_id)
    if asset is None:
        raise RecordingFailed("Файл записи не найден")
    video = absolute_path(settings, asset)
    await _stage(db, recording, RecordingStage.AUDIO)
    segments = await _recognize(providers, settings, recording, video)
    await save_segments(db, recording.id, segments)
    await _stage(db, recording, RecordingStage.STEPS)
    steps = await _segment(providers, segments, recording.duration_ms or 0)
    await _stage(db, recording, RecordingStage.SCREENSHOTS)
    await build_steps(db, providers, settings, recording, video, steps)


async def process_recording(ctx: JobContext, payload: dict[str, Any]) -> None:
    recording_id = uuid.UUID(payload["recording_id"])
    recording = await ctx.db.get(Recording, recording_id)
    if recording is None or recording.status is RecordingStatus.READY:
        return
    try:
        await _process(ctx.db, ctx.providers, ctx.settings, recording)
        return
    except RecordingFailed as exc:
        message = str(exc)
    except Exception:
        log.exception("recording %s failed", recording_id)
        message = GENERIC_ERROR
    # Failures are final for the job: the expert sees the reason and can start it again.
    await ctx.db.rollback()
    recording = await ctx.db.get(Recording, recording_id)
    if recording is not None:
        recording.status = RecordingStatus.FAILED
        recording.stage = None
        recording.error = message
        await ctx.db.commit()
