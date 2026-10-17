"""Gap lifecycle (SPEC 7.8): open → the expert answers → a gap_answer draft → approved → answered."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, Conflict, NotFound
from app.core.events import bus
from app.modules import audit
from app.modules.gaps.events import GapAnswered, GapCreated
from app.modules.gaps.models import Gap, GapStatus
from app.modules.gaps.schemas import GapOut
from app.modules.handovers.access import HandoverRole, ensure_handover_access
from app.modules.handovers.models import HandoverMember, MemberRole
from app.modules.handovers.service import get_handover, member_ids
from app.modules.identity.models import User, UserRole
from app.modules.interview.schemas import AudioOut
from app.modules.interview.service import recognize_audio
from app.modules.knowledge.domain.card_types import CardType
from app.modules.knowledge.domain.sources import CardOrigin, SourceType
from app.modules.knowledge.models import CardStatus, KnowledgeCard
from app.modules.knowledge.service import create_draft_from_source
from app.modules.org.domain.matching import normalize_name
from app.modules.privacy.service import require_consent
from app.providers.registry import Providers

ASKERS = [HandoverRole.SUCCESSOR, HandoverRole.MANAGER, HandoverRole.ADMIN]
TEAM = [HandoverRole.EXPERT, HandoverRole.MANAGER, HandoverRole.ADMIN]
ANSWERERS = [HandoverRole.EXPERT, HandoverRole.ADMIN]
MANAGERS = [HandoverRole.MANAGER, HandoverRole.ADMIN]
NOT_FOUND = "Пробел не найден"


async def _open_duplicate(db: AsyncSession, handover_id: uuid.UUID, question: str) -> Gap | None:
    """The same question asked again while the first one is still open is not a new gap."""
    wanted = normalize_name(question)
    open_gaps = (
        await db.execute(select(Gap).where(Gap.handover_id == handover_id, Gap.status == GapStatus.OPEN))
    ).scalars()
    return next((g for g in open_gaps if normalize_name(g.question) == wanted), None)


async def open_gap(
    db: AsyncSession,
    *,
    handover_id: uuid.UUID,
    question: str,
    asked_by: uuid.UUID | None,
    qa_log_id: uuid.UUID | None,
) -> Gap:
    """Creates a gap assigned to the handover's expert (no commit)."""
    duplicate = await _open_duplicate(db, handover_id, question)
    if duplicate is not None:
        return duplicate
    experts = await member_ids(db, handover_id, MemberRole.EXPERT)
    gap = Gap(
        handover_id=handover_id,
        question=question.strip(),
        asked_by=asked_by,
        qa_log_id=qa_log_id,
        assignee_id=experts[0] if experts else None,
    )
    db.add(gap)
    await db.flush()
    await bus.publish(
        db,
        GapCreated(
            gap_id=gap.id, handover_id=handover_id, user_id=asked_by, from_refusal=qa_log_id is not None
        ),
    )
    return gap


async def create_manual(
    db: AsyncSession, user: User, handover_id: uuid.UUID, question: str, qa_log_id: uuid.UUID | None
) -> Gap:
    """«Спросить эксперта» — also under an answer that did not help."""
    await ensure_handover_access(db, user, handover_id, ASKERS)
    gap = await open_gap(
        db, handover_id=handover_id, question=question, asked_by=user.id, qa_log_id=qa_log_id
    )
    await db.commit()
    return gap


async def _load(db: AsyncSession, user: User, gap_id: uuid.UUID, allowed: list[HandoverRole]) -> Gap:
    gap = await db.get(Gap, gap_id)
    if gap is None:
        raise NotFound(NOT_FOUND, code="gap_not_found")
    await ensure_handover_access(db, user, gap.handover_id, allowed)
    return gap


async def answer(db: AsyncSession, user: User, gap_id: uuid.UUID, text: str) -> Gap:
    gap = await _load(db, user, gap_id, ANSWERERS)
    if gap.status is not GapStatus.OPEN:
        raise Conflict("На этот вопрос уже ответили или он закрыт", code="gap_closed")
    if gap.answered_card_id is not None:
        card = await db.get(KnowledgeCard, gap.answered_card_id)
        if card is not None and card.status is CardStatus.DRAFT:
            raise Conflict(
                "Ответ уже ждёт проверки в разделе «Проверка карточек»", code="gap_answer_on_review"
            )
    gap.answer_text = text.strip()
    gap.answered_by = user.id
    card = await create_draft_from_source(
        db,
        handover_id=gap.handover_id,
        card_type=CardType.RULE,
        title=gap.question,
        body_md=gap.answer_text,
        origin=CardOrigin.GAP_ANSWER,
        source_type=SourceType.GAP_ANSWER,
        source_id=gap.id,
        quote=gap.answer_text,
        created_by=user.id,
    )
    gap.answered_card_id = card.id
    await audit.record(db, action="gap.answered", entity="gap", entity_id=gap.id, user_id=user.id)
    await db.commit()
    return gap


async def transcribe(
    db: AsyncSession, settings: Settings, providers: Providers, user: User, gap_id: uuid.UUID, data: bytes
) -> AudioOut:
    """Voice answer to a gap (SPEC 7.8): recognized text goes to the answer field for editing."""
    gap = await _load(db, user, gap_id, ANSWERERS)
    if gap.status is not GapStatus.OPEN:
        raise Conflict("На этот вопрос уже ответили или он закрыт", code="gap_closed")
    await require_consent(db, user.id, gap.handover_id)  # the voice is personal data, as in the interview
    return await recognize_audio(db, settings, providers, user, gap.handover_id, data)


async def dismiss(db: AsyncSession, user: User, gap_id: uuid.UUID) -> Gap:
    gap = await _load(db, user, gap_id, TEAM)
    if gap.status is GapStatus.OPEN:
        gap.status = GapStatus.DISMISSED
        await audit.record(db, action="gap.dismissed", entity="gap", entity_id=gap.id, user_id=user.id)
        await db.commit()
    return gap


async def reassign(db: AsyncSession, user: User, gap_id: uuid.UUID, assignee_id: uuid.UUID) -> Gap:
    """The expert has left: the manager gives the question to another employee (SPEC 7.8)."""
    gap = await _load(db, user, gap_id, MANAGERS)
    handover = await get_handover(db, gap.handover_id)
    assignee = await db.get(User, assignee_id)
    if assignee is None or not assignee.is_active or assignee.org_unit_id != handover.org_unit_id:
        raise AppError("Назначить можно сотрудника этого подразделения", code="bad_assignee")
    if assignee.role is UserRole.SUCCESSOR:
        raise AppError("Отвечать на пробелы может эксперт, а не преемник", code="bad_assignee")
    if await db.get(HandoverMember, (handover.id, assignee.id)) is None:
        db.add(HandoverMember(handover_id=handover.id, user_id=assignee.id, role=MemberRole.EXPERT))
    gap.assignee_id = assignee.id
    await audit.record(db, action="gap.reassigned", entity="gap", entity_id=gap.id, user_id=user.id)
    await db.commit()
    return gap


async def mark_answered(db: AsyncSession, card_id: uuid.UUID) -> None:
    gap = (await db.execute(select(Gap).where(Gap.answered_card_id == card_id))).scalar_one_or_none()
    if gap is not None and gap.status is GapStatus.OPEN:
        gap.status = GapStatus.ANSWERED
        gap.answered_at = datetime.now(UTC)
        await bus.publish(
            db, GapAnswered(gap_id=gap.id, handover_id=gap.handover_id, user_id=gap.answered_by)
        )


async def reopen_for_new_answer(db: AsyncSession, card_id: uuid.UUID) -> None:
    """The expert rejected their own answer card: the gap waits for a new answer."""
    gap = (await db.execute(select(Gap).where(Gap.answered_card_id == card_id))).scalar_one_or_none()
    if gap is not None and gap.status is GapStatus.OPEN:
        gap.answered_card_id = None


async def _describe(db: AsyncSession, gaps: list[Gap]) -> list[GapOut]:
    people = {
        u.id: u.full_name
        for u in (
            await db.execute(
                select(User).where(User.id.in_({g.asked_by for g in gaps} | {g.assignee_id for g in gaps}))
            )
        ).scalars()
    }
    card_ids = {g.answered_card_id for g in gaps if g.answered_card_id}
    card_status = dict(
        (
            await db.execute(
                select(KnowledgeCard.id, KnowledgeCard.status).where(KnowledgeCard.id.in_(card_ids))
            )
        ).all()
    )
    return [
        GapOut(
            id=g.id,
            handover_id=g.handover_id,
            question=g.question,
            status=g.status,
            asked_by_name=people.get(g.asked_by) if g.asked_by else None,
            assignee_id=g.assignee_id,
            assignee_name=people.get(g.assignee_id) if g.assignee_id else None,
            answer_text=g.answer_text,
            answered_card_id=g.answered_card_id,
            answer_on_review=g.answered_card_id is not None
            and card_status.get(g.answered_card_id) is CardStatus.DRAFT,
            created_at=g.created_at,
            answered_at=g.answered_at,
        )
        for g in gaps
    ]


async def list_gaps(
    db: AsyncSession, user: User, handover_id: uuid.UUID, status: GapStatus | None
) -> list[GapOut]:
    access = await ensure_handover_access(db, user, handover_id, list(HandoverRole))
    stmt = select(Gap).where(Gap.handover_id == handover_id).order_by(Gap.created_at.desc())
    if access.role is HandoverRole.SUCCESSOR:
        stmt = stmt.where(Gap.asked_by == user.id)  # the successor sees their own questions
    if status is not None:
        stmt = stmt.where(Gap.status == status)
    return await _describe(db, list((await db.execute(stmt)).scalars()))


async def gap_view(db: AsyncSession, user: User, gap_id: uuid.UUID) -> GapOut:
    gap = await db.get(Gap, gap_id)
    if gap is None:
        raise NotFound(NOT_FOUND, code="gap_not_found")
    access = await ensure_handover_access(db, user, gap.handover_id, list(HandoverRole))
    if access.role is HandoverRole.SUCCESSOR and gap.asked_by != user.id:
        raise NotFound(NOT_FOUND, code="gap_not_found")
    return (await _describe(db, [gap]))[0]
