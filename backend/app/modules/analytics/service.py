"""Manager dashboard (SPEC 7.9, 7.10): risk map, handover progress, product metrics, audit log.

Read-only: SQL over the tables of other modules and the `events` table.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Integer, cast, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, Forbidden, NotFound
from app.modules.analytics.domain.coverage import aspects_covered_by, coverage_approved, matrix_cell
from app.modules.analytics.domain.metrics import share
from app.modules.analytics.domain.risk import RiskThresholds, risk_level, risk_score
from app.modules.analytics.models import ProductEvent
from app.modules.analytics.schemas import (
    AspectCellOut,
    AuditEntryOut,
    HandoverProgressOut,
    MetricsOut,
    OpenGapOut,
    ProcessRiskOut,
    RiskMapOut,
)
from app.modules.audit.models import AuditLog
from app.modules.gaps.models import Gap, GapStatus
from app.modules.handovers.access import HandoverRole, ensure_handover_access
from app.modules.handovers.models import Handover, HandoverMember, HandoverProcess, HandoverStatus, MemberRole
from app.modules.handovers.service import get_handover, list_processes
from app.modules.identity.models import User, UserRole
from app.modules.interview.domain.aspects import ASPECTS
from app.modules.interview.models import InterviewSession, ProcessAspect
from app.modules.knowledge.domain.card_types import CardType
from app.modules.knowledge.models import CardStatus, KnowledgeCard
from app.modules.org import service as org
from app.modules.org.models import HolderLevel, OrgUnit, ProcessHolder
from app.modules.org.schemas import HolderOut
from app.modules.recordings.models import Recording

ACTIVE = (HandoverStatus.DRAFT, HandoverStatus.ACTIVE)
PROGRESS_READERS = [HandoverRole.MANAGER, HandoverRole.ADMIN, HandoverRole.EXPERT]
MANAGERS = [HandoverRole.MANAGER, HandoverRole.ADMIN]
_INTERVIEW_RANK = {"missing": 0, "partial": 1, "covered": 2}


def _thresholds(settings: Settings) -> RiskThresholds:
    return RiskThresholds(high=settings.risk_high, medium=settings.risk_medium)


async def _unit_for_manager(db: AsyncSession, user: User, org_unit_id: uuid.UUID | None) -> OrgUnit:
    unit_id = org_unit_id or user.org_unit_id
    if unit_id is None:
        raise AppError("Укажите подразделение", code="org_unit_required")
    if user.role is not UserRole.ADMIN and not (
        user.role is UserRole.MANAGER and user.org_unit_id == unit_id
    ):
        raise Forbidden("Панель доступна руководителю подразделения", code="dashboard_forbidden")
    unit = await db.get(OrgUnit, unit_id)
    if unit is None:
        raise NotFound("Подразделение не найдено", code="org_unit_not_found")
    return unit


async def process_rows(
    db: AsyncSession,
    settings: Settings,
    org_unit_id: uuid.UUID,
    *,
    only: set[uuid.UUID] | None = None,
    today: date | None = None,
) -> list[ProcessRiskOut]:
    """Risk and approved coverage of the unit's processes, highest risk first (SPEC 7.9)."""
    today = today or date.today()
    processes = [p for p in await org.list_processes(db, org_unit_id) if only is None or p.id in only]
    ids = [p.id for p in processes]
    if not ids:
        return []

    handovers_of: dict[uuid.UUID, list[Handover]] = defaultdict(list)
    for process_id, handover in await db.execute(
        select(HandoverProcess.process_id, Handover)
        .join(Handover, Handover.id == HandoverProcess.handover_id)
        .where(HandoverProcess.process_id.in_(ids), Handover.status.in_(ACTIVE))
    ):
        handovers_of[process_id].append(handover)
    active_ids = {h.id for hs in handovers_of.values() for h in hs}

    experts_of: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for handover_id, user_id in await db.execute(
        select(HandoverMember.handover_id, HandoverMember.user_id).where(
            HandoverMember.handover_id.in_(active_ids), HandoverMember.role == MemberRole.EXPERT
        )
    ):
        experts_of[handover_id].add(user_id)
    open_gaps_of: dict[uuid.UUID, int] = dict(
        (
            await db.execute(
                select(Gap.handover_id, func.count())
                .where(Gap.handover_id.in_(active_ids), Gap.status == GapStatus.OPEN)
                .group_by(Gap.handover_id)
            )
        ).all()
    )

    holders_of: dict[uuid.UUID, list[HolderOut]] = defaultdict(list)
    for process_id, level, user_id, full_name in await db.execute(
        select(ProcessHolder.process_id, ProcessHolder.level, User.id, User.full_name)
        .join(User, User.id == ProcessHolder.user_id)
        .where(
            ProcessHolder.process_id.in_(ids),
            ProcessHolder.level.in_([HolderLevel.OWNER, HolderLevel.KNOWS]),
            User.is_active.is_(True),
        )
        .order_by(ProcessHolder.level.desc(), User.full_name)
    ):
        holders_of[process_id].append(HolderOut(user_id=user_id, full_name=full_name, level=level))

    card_types: dict[uuid.UUID | None, set[CardType]] = defaultdict(set)
    for card_process_id, card_type in await db.execute(
        select(KnowledgeCard.process_id, KnowledgeCard.type)
        .where(KnowledgeCard.process_id.in_(ids), KnowledgeCard.status == CardStatus.APPROVED)
        .distinct()
    ):
        card_types[card_process_id].add(card_type)

    # Interview coverage of the same process may exist in several handovers: take the best status.
    not_applicable: dict[uuid.UUID, set[str]] = defaultdict(set)
    told: dict[uuid.UUID, dict[str, str]] = defaultdict(dict)
    for row in (await db.execute(select(ProcessAspect).where(ProcessAspect.process_id.in_(ids)))).scalars():
        if row.not_applicable:
            not_applicable[row.process_id].add(row.aspect)
        best = told[row.process_id].get(row.aspect, "missing")
        if _INTERVIEW_RANK.get(row.status, 0) > _INTERVIEW_RANK[best]:
            told[row.process_id][row.aspect] = row.status

    rows = []
    for process in processes:
        active = handovers_of[process.id]
        leaving = {user_id for h in active for user_id in experts_of[h.id]}
        holders = [h for h in holders_of[process.id] if h.user_id not in leaving]
        deadlines = [h.deadline for h in active if h.deadline is not None]
        deadline = min(deadlines) if deadlines else None
        days_left = (deadline - today).days if deadline else None
        coverage = coverage_approved(card_types[process.id], not_applicable[process.id])
        score = risk_score(
            criticality=process.criticality,
            holders=len(holders),
            coverage_approved=coverage,
            days_left=days_left,
        )
        covered = aspects_covered_by(card_types[process.id])
        rows.append(
            ProcessRiskOut(
                process_id=process.id,
                name=process.name,
                criticality=process.criticality,
                holders=holders,
                coverage=round(coverage, 3),
                open_gaps=sum(open_gaps_of.get(h.id, 0) for h in active),
                deadline=deadline,
                days_left=days_left,
                risk=round(score, 3),
                level=risk_level(score, _thresholds(settings)),
                aspects=[
                    AspectCellOut(
                        key=a.key,
                        label=a.label,
                        status=matrix_cell(
                            a.key,
                            covered,
                            told[process.id].get(a.key, "missing"),
                            a.key in not_applicable[process.id],
                        ),
                    )
                    for a in ASPECTS
                ],
            )
        )
    rows.sort(key=lambda r: (-r.risk, -r.criticality, r.name))
    return rows


async def risk_map(
    db: AsyncSession, settings: Settings, user: User, org_unit_id: uuid.UUID | None
) -> RiskMapOut:
    unit = await _unit_for_manager(db, user, org_unit_id)
    return RiskMapOut(
        org_unit_id=unit.id,
        org_unit_name=unit.name,
        high_threshold=settings.risk_high,
        medium_threshold=settings.risk_medium,
        processes=await process_rows(db, settings, unit.id),
    )


async def _count(db: AsyncSession, model: Any, *conditions: Any) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0


async def progress(
    db: AsyncSession, settings: Settings, user: User, handover_id: uuid.UUID
) -> HandoverProgressOut:
    """`GET /handovers/{id}/progress` (SPEC 7.9, «Прогресс передачи дел»)."""
    await ensure_handover_access(db, user, handover_id, PROGRESS_READERS)
    handover = await get_handover(db, handover_id)
    sessions, interview_seconds = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(InterviewSession.active_seconds), 0)).where(
                InterviewSession.handover_id == handover_id
            )
        )
    ).one()
    recordings, recording_ms = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(Recording.duration_ms), 0)).where(
                Recording.handover_id == handover_id
            )
        )
    ).one()
    by_status = dict(
        (
            await db.execute(
                select(KnowledgeCard.status, func.count())
                .where(KnowledgeCard.handover_id == handover_id)
                .group_by(KnowledgeCard.status)
            )
        ).all()
    )
    review_seconds = await db.scalar(
        select(func.coalesce(func.sum(KnowledgeCard.review_seconds), 0)).where(
            KnowledgeCard.handover_id == handover_id
        )
    )
    process_ids = {p.id for p in await list_processes(db, handover_id)}
    deadline = handover.deadline
    return HandoverProgressOut(
        handover_id=handover_id,
        deadline=deadline,
        days_left=(deadline - date.today()).days if deadline else None,
        interview_sessions=sessions,
        interview_minutes=round(interview_seconds / 60),
        recordings=recordings,
        recording_minutes=round((recording_ms or 0) / 60_000),
        review_minutes=round((review_seconds or 0) / 60),
        cards_draft=by_status.get(CardStatus.DRAFT, 0),
        cards_approved=by_status.get(CardStatus.APPROVED, 0),
        cards_rejected=by_status.get(CardStatus.REJECTED, 0),
        open_gaps=await _count(db, Gap, Gap.handover_id == handover_id, Gap.status == GapStatus.OPEN),
        processes=await process_rows(db, settings, handover.org_unit_id, only=process_ids),
    )


async def metrics(
    db: AsyncSession,
    settings: Settings,
    user: User,
    *,
    handover_id: uuid.UUID | None,
    org_unit_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> MetricsOut:
    """`GET /dashboard/metrics` (SPEC 7.10): one handover or all handovers of the unit, for a period."""
    if handover_id is not None:
        await ensure_handover_access(db, user, handover_id, MANAGERS)
        handover = await get_handover(db, handover_id)
        unit_id = handover.org_unit_id
        handover_ids = [handover_id]
        process_ids: set[uuid.UUID] | None = {p.id for p in await list_processes(db, handover_id)}
    else:
        unit_id = (await _unit_for_manager(db, user, org_unit_id)).id
        handover_ids = list(
            (await db.execute(select(Handover.id).where(Handover.org_unit_id == unit_id))).scalars()
        )
        process_ids = None

    scope: list[ColumnElement[bool]] = [ProductEvent.handover_id.in_(handover_ids)]
    if date_from is not None:
        scope.append(ProductEvent.at >= datetime.combine(date_from, time.min, UTC))
    if date_to is not None:
        scope.append(ProductEvent.at < datetime.combine(date_to + timedelta(days=1), time.min, UTC))
    props = ProductEvent.props

    def named(name: str) -> list[Any]:
        return [*scope, ProductEvent.name == name]

    async def total(name: str) -> int:
        return await _count(db, ProductEvent, *named(name))

    async def summed(name: str, key: str) -> int:
        value = await db.scalar(
            select(func.coalesce(func.sum(cast(props[key].astext, Integer)), 0)).where(*named(name))
        )
        return int(value or 0)

    async def distinct_cards(*conditions: Any) -> int:
        value = await db.scalar(
            select(func.count(distinct(props["card_id"].astext))).where(*named("card_approved"), *conditions)
        )
        return int(value or 0)

    interview_s = await summed("interview_session_finished", "active_seconds")
    recording_ms = await summed("recording_processed", "duration_ms")
    review_s = await summed("review_time", "seconds")
    generated = await total("card_generated")
    statuses: dict[str, int] = dict(
        (
            await db.execute(
                select(props["status"].astext, func.count())
                .where(*named("answer_shown"))
                .group_by(text("1"))  # the same `->>` with another bind parameter would not match
            )
        ).all()
    )
    questions = sum(statuses.values())
    feedback = await total("answer_feedback")
    helpful = await _count(db, ProductEvent, *named("answer_feedback"), props["helpful"].astext == "true")
    p95 = await db.scalar(
        select(func.percentile_cont(0.95).within_group(cast(props["latency_ms"].astext, Integer))).where(
            *named("answer_shown")
        )
    )

    open_gaps = [Gap.handover_id.in_(handover_ids), Gap.status == GapStatus.OPEN]
    top = list(
        (await db.execute(select(Gap).where(*open_gaps).order_by(Gap.created_at.desc()).limit(5))).scalars()
    )
    key = [
        r.coverage for r in await process_rows(db, settings, unit_id, only=process_ids) if r.criticality == 3
    ]

    return MetricsOut(
        handover_id=handover_id,
        org_unit_id=unit_id,
        date_from=date_from,
        date_to=date_to,
        expert_minutes=round((interview_s + recording_ms / 1000 + review_s) / 60),
        interview_minutes=round(interview_s / 60),
        recording_minutes=round(recording_ms / 60_000),
        review_minutes=round(review_s / 60),
        interview_turns=await total("interview_turn"),
        recordings_processed=await total("recording_processed"),
        cards_generated=generated,
        cards_dropped_no_evidence=await total("card_dropped_no_evidence"),
        cards_approved=await distinct_cards(),
        cards_approved_edited=await distinct_cards(props["edited"].astext == "true"),
        cards_rejected=await total("card_rejected"),
        # Manual cards are not generated; events written before M4 have no origin.
        approved_share=share(
            await distinct_cards(func.coalesce(props["origin"].astext, "") != "manual"), generated
        ),
        questions=questions,
        answered_share=share(statuses.get("answered", 0), questions),
        partial_share=share(statuses.get("partial", 0), questions),
        refused_share=share(statuses.get("refused", 0), questions),
        helpful_share=share(helpful, feedback),
        feedback_count=feedback,
        answer_latency_p95_ms=round(p95) if p95 is not None else None,
        gaps_created=await total("gap_created"),
        gaps_answered=await total("gap_answered"),
        gaps_open_now=await _count(db, Gap, *open_gaps),
        key_processes_coverage=sum(key) / len(key) if key else None,
        top_open_gaps=[
            OpenGapOut(id=g.id, handover_id=g.handover_id, question=g.question, created_at=g.created_at)
            for g in top
        ],
    )


async def audit_log(
    db: AsyncSession,
    user: User,
    *,
    entity: str | None,
    entity_id: uuid.UUID | None,
    limit: int,
) -> list[AuditEntryOut]:
    """`GET /audit` (SPEC 8): admin sees everything, a manager — actions of their unit's employees."""
    stmt = (
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.user_id)
        .order_by(AuditLog.at.desc(), AuditLog.id)
        .limit(limit)
    )
    if user.role is UserRole.MANAGER:
        if user.org_unit_id is None:
            return []
        stmt = stmt.where(User.org_unit_id == user.org_unit_id)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    return [
        AuditEntryOut(
            id=row.id,
            at=row.at,
            user_id=row.user_id,
            user_name=name,
            action=row.action,
            entity=row.entity,
            entity_id=row.entity_id,
            meta=row.meta,
        )
        for row, name in await db.execute(stmt)
    ]
