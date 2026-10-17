"""`make seed-demo`: loads fictional demo data (SPEC 13.1).

Idempotent in the «known state» sense: demo users and processes are upserted, demo handovers are
deleted and created again with a finished interview, process coverage and cards.
Every card quote is checked against the interview text — the seed fails if a quote is not found.

Run from backend/ (the `app` package must be importable): `uv run python ../seed/seed.py`.
"""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.core.prompts import get_prompts
from app.core.security import hash_password
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


async def _upsert_processes(db: AsyncSession, raw_processes: list[dict[str, Any]], unit: OrgUnit) -> dict[str, Process]:
    processes: dict[str, Process] = {}
    for raw in raw_processes:
        process = (
            await db.execute(select(Process).where(Process.org_unit_id == unit.id, Process.name == raw["name"]))
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
    intro = get_prompts().render(
        "interview_intro", expert_name=expert.full_name, successor_name=successor.full_name
    ).text
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
    db: AsyncSession, handover: Handover, processes: dict[str, Process], coverage: dict[str, dict[str, list[str]]]
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
) -> dict[str, int]:
    now = datetime.now(UTC)
    counts = {"approved": 0, "draft": 0}
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
        counts[status.value] += 1
    await db.flush()
    return counts


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
    await db.execute(delete(Handover).where(Handover.org_unit_id == unit.id))
    await db.execute(delete(ProcessHolder).where(ProcessHolder.process_id.in_([p.id for p in processes.values()])))
    for raw in demo["processes"]:
        for key in raw["also_known_by"]:
            db.add(ProcessHolder(process_id=processes[raw["key"]].id, user_id=users[key].id, level=HolderLevel.KNOWS))
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
    db.add(Consent(user_id=expert.id, handover_id=handover.id, text_version=text.version, text_hash=text.hash))
    messages = await _seed_interview(db, handover, expert, successor, interview)
    await _seed_coverage(db, handover, processes, interview["coverage"])
    counts = await _seed_cards(db, handover, expert, processes, messages, cards["cards"])
    await db.commit()
    return {
        "users_created": len({u.email for u in users.values()} - existing_users),
        "users_total": len(users),
        "processes": len(processes),
        "messages": len(messages),
        "cards_approved": counts["approved"],
        "cards_draft": counts["draft"],
    }


async def main() -> None:
    async with get_sessionmaker()() as db:
        result = await seed(db)
    await dispose_engine()
    print(f"Демо-данные загружены: {result}. Пароль демо-учёток: {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
