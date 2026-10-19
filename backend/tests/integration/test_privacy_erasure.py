"""Deleting data: files, steps, messages go; cards without sources are archived."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.storage import Asset, AssetKind, absolute_path
from app.modules.audit.models import AuditLog
from app.modules.gaps.models import Gap, GapStatus
from app.modules.identity.models import UserRole
from app.modules.interview.models import InterviewMessage, InterviewSession, MessageRole
from app.modules.knowledge.domain.sources import CardOrigin, SourceType
from app.modules.knowledge.models import CardSource, CardStatus, KnowledgeCard
from app.modules.privacy.models import Consent
from app.modules.privacy.retention import purge_expired_media
from app.modules.recordings.models import (
    Recording,
    RecordingStatus,
    RecordingStep,
    SegmentSource,
    TranscriptSegment,
)
from app.modules.search.indexer import index_card
from app.modules.search.models import CardChunk
from tests.factories import (
    give_consent,
    login,
    make_asset,
    make_handover,
    make_org_unit,
    make_process,
    make_user,
)


async def make_card(
    db: AsyncSession,
    handover_id: uuid.UUID,
    title: str,
    sources: list[tuple[SourceType, uuid.UUID]],
    **kw: Any,
) -> KnowledgeCard:
    card = KnowledgeCard(
        handover_id=handover_id,
        type=kw.pop("type", "rule"),
        title=title,
        summary="Суть",
        body_md="Текст",
        origin=kw.pop("origin", CardOrigin.INTERVIEW),
        status=kw.pop("status", CardStatus.APPROVED),
        **kw,
    )
    db.add(card)
    await db.flush()
    for source_type, source_id in sources:
        db.add(
            CardSource(
                card_id=card.id, source_type=source_type, source_id=source_id, quote="цитата из источника"
            )
        )
    await db.flush()
    return card


@pytest.fixture
async def world(db: AsyncSession, app: FastAPI) -> dict[str, Any]:
    unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    colleague = await make_user(db, UserRole.EXPERT, org_unit=unit)
    successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    process = await make_process(db, unit, "Оформление пересдач")
    handover = await make_handover(
        db, org_unit=unit, manager=manager, expert=expert, successor=successor, processes=[process]
    )
    await give_consent(db, expert, handover)

    session = InterviewSession(handover_id=handover.id, expert_id=expert.id)
    db.add(session)
    await db.flush()
    voice = await make_asset(db, AssetKind.AUDIO, expert.id, handover.id)
    message = InterviewMessage(
        session_id=session.id,
        seq=2,
        role=MessageRole.EXPERT,
        content="Направление печатаю в двух экземплярах.",
        audio_asset_id=voice.id,
    )
    db.add(message)
    unsent_voice = await make_asset(db, AssetKind.AUDIO, expert.id, handover.id)  # recognized, never sent

    video = await make_asset(db, AssetKind.VIDEO, expert.id, handover.id)
    screenshot = await make_asset(db, AssetKind.IMAGE, expert.id, handover.id)  # as the pipeline does
    recording = Recording(
        handover_id=handover.id,
        video_asset_id=video.id,
        title="Пересдача",
        status=RecordingStatus.READY,
        created_by=expert.id,
    )
    db.add(recording)
    await db.flush()
    step = RecordingStep(
        recording_id=recording.id, idx=1, title="Найти студента", action="Ввести фамилию",
        start_ms=0, end_ms=5000, screenshot_asset_id=screenshot.id, screenshot_blurred=True,
    )  # fmt: skip
    segment = TranscriptSegment(
        source_type=SegmentSource.RECORDING,
        source_id=recording.id,
        start_ms=0,
        end_ms=5000,
        text="Ищу студента",
    )
    db.add_all([step, segment])
    await db.flush()

    gap = Gap(
        handover_id=handover.id, question="Куда звонить, если нет ведомости?", status=GapStatus.ANSWERED,
        answer_text="В деканат, методисту.", answered_by=expert.id, answered_at=datetime.now(UTC),
    )  # fmt: skip
    db.add(gap)
    await db.flush()

    only_step = await make_card(
        db,
        handover.id,
        "Инструкция по записи",
        [(SourceType.RECORDING_STEP, step.id)],
        origin=CardOrigin.RECORDING,
    )
    step_and_message = await make_card(
        db,
        handover.id,
        "Два экземпляра",
        [(SourceType.RECORDING_STEP, step.id), (SourceType.INTERVIEW_MESSAGE, message.id)],
    )
    only_message = await make_card(db, handover.id, "Печать", [(SourceType.INTERVIEW_MESSAGE, message.id)])
    draft_from_message = await make_card(
        db, handover.id, "Черновик", [(SourceType.INTERVIEW_MESSAGE, message.id)], status=CardStatus.DRAFT
    )
    gap_card = await make_card(
        db, handover.id, gap.question, [(SourceType.GAP_ANSWER, gap.id)], origin=CardOrigin.GAP_ANSWER
    )
    gap.answered_card_id = gap_card.id
    manual = await make_card(db, handover.id, "Вручную", [], origin=CardOrigin.MANUAL)
    await db.commit()
    for card in (only_step, step_and_message, only_message, gap_card):
        await index_card(db, app.state.providers, card.id)
    await db.commit()
    return locals()


async def _status(db: AsyncSession, card: KnowledgeCard) -> tuple[CardStatus, str | None]:
    row = (
        await db.execute(
            select(KnowledgeCard.status, KnowledgeCard.archived_reason).where(KnowledgeCard.id == card.id)
        )
    ).one()
    return row[0], row[1]


async def _count(db: AsyncSession, model: Any) -> int:
    return await db.scalar(select(func.count()).select_from(model)) or 0


async def _chunks(db: AsyncSession, card: KnowledgeCard) -> int:
    return (
        await db.scalar(select(func.count()).select_from(CardChunk).where(CardChunk.card_id == card.id)) or 0
    )


async def _sources(db: AsyncSession, card: KnowledgeCard) -> list[SourceType]:
    return list(
        (await db.execute(select(CardSource.source_type).where(CardSource.card_id == card.id))).scalars()
    )


async def _asset(db: AsyncSession, asset: Asset) -> Asset:
    row = await db.scalar(select(Asset).where(Asset.id == asset.id).execution_options(populate_existing=True))
    assert row is not None
    return row


async def test_deleting_a_recording_removes_files_steps_and_archives_cards_without_sources(
    client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]
) -> None:
    w = world
    video_path, shot_path = (
        absolute_path(get_settings(), w["video"]),
        absolute_path(get_settings(), w["screenshot"]),
    )
    assert video_path.is_file() and shot_path.is_file()

    await login(client, w["expert"])
    response = await client.delete(f"/api/recordings/{w['recording'].id}")
    assert response.status_code == 204, response.text

    assert not video_path.exists() and not shot_path.exists()
    assert (await _asset(db, w["video"])).deleted_at is not None
    assert (await _asset(db, w["screenshot"])).deleted_at is not None
    assert await _count(db, Recording) == 0
    assert await _count(db, RecordingStep) == 0
    assert await _count(db, TranscriptSegment) == 0

    assert await _status(db, w["only_step"]) == (CardStatus.ARCHIVED, "source_deleted")
    assert await _chunks(db, w["only_step"]) == 0  # gone from the assistant's index
    # A card with another source stays; the deleted link disappears.
    assert await _status(db, w["step_and_message"]) == (CardStatus.APPROVED, None)
    assert await _sources(db, w["step_and_message"]) == [SourceType.INTERVIEW_MESSAGE]
    assert await _chunks(db, w["step_and_message"]) > 0
    assert await _status(db, w["only_message"]) == (CardStatus.APPROVED, None)

    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "recording.deleted"))
    assert entry is not None and entry.user_id == w["expert"].id and entry.entity_id == w["recording"].id

    assert (await client.get(f"/api/recordings/{w['recording'].id}")).status_code == 404


async def test_only_the_author_or_admin_deletes_a_recording(
    client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]
) -> None:
    w = world
    url = f"/api/recordings/{w['recording'].id}"
    await login(client, w["successor"])
    assert (await client.delete(url)).status_code == 403
    await login(client, w["manager"])
    assert (await client.delete(url)).status_code == 403
    await login(client, w["colleague"])  # not a member of the handover
    assert (await client.delete(url)).status_code == 403
    assert await _count(db, Recording) == 1


async def test_a_recording_in_processing_is_not_deleted(
    client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]
) -> None:
    w = world
    w["recording"].status = RecordingStatus.PROCESSING
    await db.commit()
    await login(client, w["expert"])
    response = await client.delete(f"/api/recordings/{w['recording'].id}")
    assert response.status_code == 409
    assert response.json()["code"] == "recording_busy"


async def test_my_data_shows_what_is_stored(client: httpx.AsyncClient, world: dict[str, Any]) -> None:
    w = world
    await login(client, w["expert"])
    data = (await client.get("/api/privacy/my-data", params={"handover_id": str(w["handover"].id)})).json()
    assert data["consent"] is not None
    assert data["counts"] == {
        "interview_messages": 1,
        "recordings": 1,
        "gap_answers": 1,
        "files": 4,  # voice, unsent voice, video, screenshot
        "files_bytes": 20,
    }
    await login(client, w["successor"])
    assert (
        await client.get("/api/privacy/my-data", params={"handover_id": str(w["handover"].id)})
    ).status_code == 403


async def test_erasing_my_data_cascades(
    client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]
) -> None:
    w = world
    await login(client, w["expert"])
    response = await client.delete("/api/privacy/my-data", params={"handover_id": str(w["handover"].id)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"] == {"interview_messages": 1, "recordings": 1, "gap_answers": 1}
    assert body["files"] == 4  # voice, unsent voice, video, screenshot

    for name in ("voice", "unsent_voice", "video", "screenshot"):
        asset = await _asset(db, w[name])
        assert asset.deleted_at is not None, name
        assert not absolute_path(get_settings(), asset).exists(), name
    assert await _count(db, InterviewSession) == 0
    assert await _count(db, InterviewMessage) == 0
    assert await _count(db, Recording) == 0

    for name in ("only_step", "step_and_message", "only_message", "draft_from_message", "gap_card"):
        assert await _status(db, w[name]) == (CardStatus.ARCHIVED, "source_deleted"), name
        assert await _chunks(db, w[name]) == 0, name
    assert await _status(db, w["manual"]) == (CardStatus.APPROVED, None)  # had no sources at all

    gap = await db.scalar(select(Gap).where(Gap.id == w["gap"].id).execution_options(populate_existing=True))
    assert gap is not None
    assert gap.status is GapStatus.OPEN and gap.answer_text is None and gap.answered_card_id is None

    # The consent record stays: it is the trace of what was agreed and when.
    assert await _count(db, Consent) == 1
    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "data.erased"))
    assert entry is not None and entry.meta["files"] == 4 and entry.meta["recordings"] == 1

    again = await client.delete("/api/privacy/my-data", params={"handover_id": str(w["handover"].id)})
    assert again.json() == {
        "counts": {"interview_messages": 0, "recordings": 0, "gap_answers": 0},
        "files": 0,
        "sources": 0,
    }


async def test_raw_media_retention(
    client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]
) -> None:
    w = world
    old = datetime.now(UTC) - timedelta(days=get_settings().retention_days_raw_media + 1)
    for name in ("video", "voice", "screenshot"):
        w[name].created_at = old
    await db.commit()

    assert await purge_expired_media(db, get_settings()) == 2
    await db.commit()
    assert (await _asset(db, w["video"])).deleted_at is not None
    assert (await _asset(db, w["voice"])).deleted_at is not None
    assert (await _asset(db, w["unsent_voice"])).deleted_at is None  # not expired yet
    screenshot = await _asset(db, w["screenshot"])
    assert screenshot.deleted_at is None and absolute_path(get_settings(), screenshot).is_file()
    assert await purge_expired_media(db, get_settings()) == 0  # idempotent

    # Steps and cards stay; the page says the video is gone, sources no longer offer it.
    await login(client, w["expert"])
    recording = (await client.get(f"/api/recordings/{w['recording'].id}")).json()
    assert recording["video_available"] is False and len(recording["steps"]) == 1
    card = (await client.get(f"/api/cards/{w['only_step'].id}")).json()
    [source] = card["sources"]
    assert source["available"] is True and "video_asset_id" not in source["link"]
    assert (await client.get(f"/api/assets/{w['video'].id}")).status_code == 404
