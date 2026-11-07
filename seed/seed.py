"""`make seed-demo`: loads fictional demo data.

Idempotent in the «known state» sense: demo users and processes are upserted, demo handovers are
deleted and created again with a finished interview, process coverage and cards.
Every card quote is checked against the interview text — the seed fails if a quote is not found.

Run from backend/ (the `app` package must be importable): `uv run python ../seed/seed.py`.
"""

import asyncio
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.core.prompts import get_prompts
from app.core.security import hash_password
from app.core.storage import Asset, AssetKind, absolute_path, store_stream
from app.modules.gaps.models import Gap
from app.modules.handovers.models import Handover, HandoverMember, HandoverReason, HandoverStatus, MemberRole
from app.modules.handovers.service import link_processes
from app.modules.identity.models import User, UserRole
from app.modules.interview.models import (
    InterviewMessage,
    InterviewSession,
    MessageRole,
    ProcessAspect,
    SessionStatus,
)
from app.modules.knowledge.domain.quotes import find_quote
from app.modules.knowledge.domain.sources import CardOrigin, SourceType
from app.modules.knowledge.models import CardSource, CardStatus, KnowledgeCard
from app.modules.org.models import HolderLevel, OrgUnit, Process, ProcessFrequency, ProcessHolder
from app.modules.privacy.models import Consent
from app.modules.privacy.service import current_text
from app.modules.recordings.domain.steps import StepDraft, fix_steps
from app.modules.recordings.models import Recording, RecordingStatus
from app.modules.recordings.pipeline import build_steps, save_segments
from app.modules.search.indexer import index_card
from app.providers.asr.base import Segment
from app.providers.registry import Providers, build_providers
from app.wiring import import_models

DATA = Path(__file__).resolve().parent / "data"
DEMO_PASSWORD = "demo1234"


def load(name: str) -> dict[str, Any]:
    return json.loads((DATA / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


class SeedError(Exception):
    pass


async def _upsert_users(db: AsyncSession, raw_users: list[dict[str, Any]], unit: OrgUnit) -> dict[str, User]:
    password_hash = hash_password(DEMO_PASSWORD)
    users: dict[str, User] = {}
    for raw in raw_users:
        user = (await db.execute(select(User).where(User.email == raw["email"]))).scalar_one_or_none()
        if user is None:
            user = User(email=raw["email"])
            db.add(user)
        user.full_name = raw["full_name"]
        user.role = UserRole(raw["role"])
        user.password_hash = password_hash
        user.is_active = True
        user.org_unit_id = unit.id
        users[raw["key"]] = user
    await db.flush()
    return users


async def _upsert_processes(
    db: AsyncSession, raw_processes: list[dict[str, Any]], unit: OrgUnit
) -> dict[str, Process]:
    processes: dict[str, Process] = {}
    for raw in raw_processes:
        process = (
            await db.execute(
                select(Process).where(Process.org_unit_id == unit.id, Process.name == raw["name"])
            )
        ).scalar_one_or_none()
        if process is None:
            process = Process(org_unit_id=unit.id, name=raw["name"])
            db.add(process)
        process.description = raw["description"]
        process.frequency = ProcessFrequency(raw["frequency"])
        process.criticality = raw["criticality"]
        processes[raw["key"]] = process
    await db.flush()
    return processes


async def _seed_interview(
    db: AsyncSession, handover: Handover, expert: User, successor: User, interview: dict[str, Any]
) -> dict[int, InterviewMessage]:
    started = datetime.now(UTC) - timedelta(days=interview["started_days_ago"])
    session = InterviewSession(
        handover_id=handover.id,
        expert_id=expert.id,
        status=SessionStatus.FINISHED,
        phase="done",
        state_json={"schema_version": 1, "phase": "done"},
        started_at=started,
        finished_at=started + timedelta(minutes=40),
        last_activity_at=started + timedelta(minutes=40),
        active_seconds=interview["active_seconds"],
        extracted_at=started + timedelta(minutes=41),  # cards below stand for the extraction result
    )
    db.add(session)
    await db.flush()
    intro = (
        get_prompts()
        .render("interview_intro", expert_name=expert.full_name, successor_name=successor.full_name)
        .text
    )
    rows = [{"seq": 1, "role": "interviewer", "text": intro}, *interview["messages"]]
    messages: dict[int, InterviewMessage] = {}
    for raw in rows:
        message = InterviewMessage(
            session_id=session.id,
            seq=raw["seq"],
            role=MessageRole(raw["role"]),
            content=raw["text"],
            meta={},
            created_at=started + timedelta(minutes=raw["seq"]),
        )
        db.add(message)
        messages[raw["seq"]] = message
    await db.flush()
    return messages


async def _seed_coverage(
    db: AsyncSession,
    handover: Handover,
    processes: dict[str, Process],
    coverage: dict[str, dict[str, list[str]]],
) -> None:
    for key, statuses in coverage.items():
        for status, aspects in statuses.items():
            for aspect in aspects:
                db.add(
                    ProcessAspect(
                        handover_id=handover.id, process_id=processes[key].id, aspect=aspect, status=status
                    )
                )
    await db.flush()


async def _seed_cards(
    db: AsyncSession,
    handover: Handover,
    expert: User,
    processes: dict[str, Process],
    messages: dict[int, InterviewMessage],
    cards: list[dict[str, Any]],
) -> list[KnowledgeCard]:
    now = datetime.now(UTC)
    created: list[KnowledgeCard] = []
    for i, raw in enumerate(cards):
        status = CardStatus(raw["status"])
        card = KnowledgeCard(
            handover_id=handover.id,
            process_id=processes[raw["process"]].id if raw["process"] else None,
            type=raw["type"],
            title=raw["title"],
            summary=raw["summary"],
            body_md=raw["body_md"],
            applies_when=raw["applies_when"],
            status=status,
            origin=CardOrigin.INTERVIEW,
            approved_by=expert.id if status is CardStatus.APPROVED else None,
            approved_at=now - timedelta(hours=20 - i % 20) if status is CardStatus.APPROVED else None,
            review_seconds=25 + (i * 7) % 60 if status is CardStatus.APPROVED else 0,
        )
        db.add(card)
        await db.flush()
        for quote in raw["quotes"]:
            message = messages.get(quote["seq"])
            if message is None or message.role is not MessageRole.EXPERT:
                raise SeedError(f"Карточка «{raw['title']}»: реплики эксперта {quote['seq']} нет")
            match = find_quote(quote["text"], message.content)
            if match is None:
                raise SeedError(f"Карточка «{raw['title']}»: цитата не найдена в реплике {quote['seq']}")
            db.add(
                CardSource(
                    card_id=card.id,
                    source_type=SourceType.INTERVIEW_MESSAGE,
                    source_id=message.id,
                    quote=match.text,
                )
            )
        created.append(card)
    await db.flush()
    return created


async def _seed_recording(
    db: AsyncSession,
    providers: Providers,
    handover: Handover,
    expert: User,
    processes: dict[str, Process],
    raw: dict[str, Any],
) -> KnowledgeCard:
    """The demo recording goes through the real screenshot/blur code; transcript and steps come from
    `recording.json` (recorded by demo/record_demo.mjs), so no speech model or LLM is needed."""
    settings = get_settings()
    with (DATA / "recording" / "retake.webm").open("rb") as video:
        asset = await asyncio.to_thread(
            store_stream,
            settings,
            video,
            expected_kind=AssetKind.VIDEO,
            max_bytes=settings.recording_max_mb * 1024 * 1024,
            owner_id=expert.id,
            handover_id=handover.id,
        )
    db.add(asset)
    recording = Recording(
        handover_id=handover.id,
        process_id=processes[raw["process"]].id,
        video_asset_id=asset.id,
        title=raw["title"],
        status=RecordingStatus.PROCESSING,
        duration_ms=raw["duration_ms"],
        created_by=expert.id,
    )
    db.add(recording)
    await db.flush()
    await save_segments(
        db, recording.id, [Segment(s["start_ms"], s["end_ms"], s["text"]) for s in raw["segments"]]
    )
    steps = fix_steps(
        [
            StepDraft(s["title"], s["action"], s["rationale"], s["start_ms"], s["end_ms"])
            for s in raw["steps"]
        ],
        raw["duration_ms"],
    )
    card = await build_steps(db, providers, settings, recording, absolute_path(settings, asset), steps)
    card.status = (
        CardStatus.APPROVED
    )  # the expert has already checked it, so the assistant can cite the video
    card.approved_by = expert.id
    card.approved_at = datetime.now(UTC)
    await db.flush()
    return card


async def _drop_files(db: AsyncSession, handover_ids: list[uuid.UUID]) -> None:
    """Files of the demo handovers that are about to be recreated (rows go by cascade, files do not)."""
    settings = get_settings()
    for asset in (await db.execute(select(Asset).where(Asset.handover_id.in_(handover_ids)))).scalars():
        absolute_path(settings, asset).unlink(missing_ok=True)


async def seed(db: AsyncSession) -> dict[str, int]:
    import_models()
    demo, interview, cards = load("demo.json"), load("interview.json"), load("cards.json")

    unit = (await db.execute(select(OrgUnit).where(OrgUnit.name == demo["org_unit"]))).scalar_one_or_none()
    if unit is None:
        unit = OrgUnit(name=demo["org_unit"])
        db.add(unit)
        await db.flush()
    existing_users = {e for e in (await db.execute(select(User.email))).scalars()}
    users = await _upsert_users(db, demo["users"], unit)
    processes = await _upsert_processes(db, demo["processes"], unit)

    # Known state: demo handovers (with sessions, cards, consents — by cascade) are recreated.
    old = list((await db.execute(select(Handover.id).where(Handover.org_unit_id == unit.id))).scalars())
    await _drop_files(db, old)
    await db.execute(delete(Handover).where(Handover.org_unit_id == unit.id))
    await db.execute(
        delete(ProcessHolder).where(ProcessHolder.process_id.in_([p.id for p in processes.values()]))
    )
    for raw in demo["processes"]:
        for key in raw["also_known_by"]:
            db.add(
                ProcessHolder(
                    process_id=processes[raw["key"]].id, user_id=users[key].id, level=HolderLevel.KNOWS
                )
            )
    await db.flush()

    expert, successor = users["expert"], users["successor"]
    handover = Handover(
        org_unit_id=unit.id,
        manager_id=users["manager"].id,
        reason=HandoverReason(demo["handover"]["reason"]),
        deadline=date.today() + timedelta(days=demo["handover"]["deadline_in_days"]),
        status=HandoverStatus.ACTIVE,
    )
    db.add(handover)
    await db.flush()
    db.add(HandoverMember(handover_id=handover.id, user_id=expert.id, role=MemberRole.EXPERT))
    db.add(HandoverMember(handover_id=handover.id, user_id=successor.id, role=MemberRole.SUCCESSOR))
    await db.flush()
    await link_processes(db, handover, [p.id for p in processes.values()])

    text = current_text(get_settings())
    db.add(
        Consent(user_id=expert.id, handover_id=handover.id, text_version=text.version, text_hash=text.hash)
    )
    messages = await _seed_interview(db, handover, expert, successor, interview)
    await _seed_coverage(db, handover, processes, interview["coverage"])
    created = await _seed_cards(db, handover, expert, processes, messages, cards["cards"])
    providers = build_providers(get_settings())
    recording = load("recording.json")
    created.append(await _seed_recording(db, providers, handover, expert, processes, recording))
    approved = [c for c in created if c.status is CardStatus.APPROVED]

    # The assistant searches the index, so approved cards are indexed right away (configured embeddings).
    chunks = 0
    for card in approved:
        chunks += await index_card(db, providers, card.id)

    for question in demo["open_gaps"]:
        db.add(Gap(handover_id=handover.id, question=question, asked_by=successor.id, assignee_id=expert.id))
    await db.commit()
    return {
        "users_created": len({u.email for u in users.values()} - existing_users),
        "users_total": len(users),
        "processes": len(processes),
        "messages": len(messages),
        "cards_approved": len(approved),
        "cards_draft": len(created) - len(approved),
        "chunks": chunks,
        "recording_steps": len(recording["steps"]),
        "open_gaps": len(demo["open_gaps"]),
    }


async def main() -> None:
    async with get_sessionmaker()() as db:
        result = await seed(db)
    await dispose_engine()
    print(f"Демо-данные загружены: {result}. Пароль демо-учёток: {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
