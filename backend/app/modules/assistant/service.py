"""Assistant use cases: ask (stores qa_logs, publishes events), feedback, history."""

import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound
from app.core.events import bus
from app.modules.assistant.events import AnswerFeedback, AnswerRefused, AnswerShown
from app.modules.assistant.models import AnswerStatus, QaLog
from app.modules.assistant.pipeline import answer_question
from app.modules.assistant.schemas import AnswerOut, SourceRef, Verification
from app.modules.handovers.access import HandoverRole, ensure_handover_access
from app.modules.handovers.models import MemberRole
from app.modules.handovers.service import get_handover, member_ids
from app.modules.identity.models import User
from app.providers.registry import Providers

ASKERS = [HandoverRole.SUCCESSOR, HandoverRole.MANAGER, HandoverRole.ADMIN]
HISTORY_LIMIT = 30


def to_out(log: QaLog, forwarded_to: str | None = None) -> AnswerOut:
    return AnswerOut(
        qa_id=log.id,
        question=log.question,
        status=log.status,
        answer=log.answer,
        sources=[SourceRef.model_validate(s) for s in log.sources],
        groundedness=log.groundedness,
        verification=cast(Verification, log.verification),  # validated by pydantic
        refusal_reason=log.refusal_reason,
        forwarded_to=forwarded_to,
        feedback=log.feedback,
        created_at=log.created_at,
    )


async def _forwarded_to(db: AsyncSession, handover_id: uuid.UUID) -> str:
    """The expert who will see the gap, or the manager if there is no expert."""
    experts = await member_ids(db, handover_id, MemberRole.EXPERT)
    user = await db.get(User, experts[0]) if experts else None
    if user is None:
        user = await db.get(User, (await get_handover(db, handover_id)).manager_id)
    return user.full_name if user else "руководителю"


async def ask(
    db: AsyncSession,
    providers: Providers,
    settings: Settings,
    user: User,
    handover_id: uuid.UUID,
    question: str,
) -> AnswerOut:
    await ensure_handover_access(db, user, handover_id, ASKERS)
    question = question.strip()
    result = await answer_question(db, providers, settings, handover_id, question)
    log = QaLog(
        user_id=user.id,
        handover_id=handover_id,
        question=question,
        answer=result.answer,
        status=result.status,
        refusal_reason=result.refusal_reason,
        verification=result.verification,
        cited_card_ids=[s.card_id for s in result.sources],
        sources=[s.public() for s in result.sources],
        retrieval=result.retrieval,
        groundedness=result.groundedness,
        latency_ms=result.latency_ms,
        prompt_version=result.prompt_version,
        model=result.model,
    )
    db.add(log)
    await db.flush()
    forwarded = None
    if result.status is AnswerStatus.REFUSED:
        forwarded = await _forwarded_to(db, handover_id)
        await bus.publish(
            db,
            AnswerRefused(
                qa_id=log.id,
                handover_id=handover_id,
                user_id=user.id,
                question=question,
                latency_ms=result.latency_ms,
            ),
        )
    else:
        await bus.publish(
            db,
            AnswerShown(
                qa_id=log.id,
                handover_id=handover_id,
                user_id=user.id,
                status=result.status.value,
                groundedness=result.groundedness,
                latency_ms=result.latency_ms,
            ),
        )
    await db.commit()
    return to_out(log, forwarded)


async def feedback(
    db: AsyncSession, user: User, qa_id: uuid.UUID, helpful: bool, comment: str | None
) -> AnswerOut:
    log = await db.get(QaLog, qa_id)
    if log is None or log.user_id != user.id:
        raise NotFound("Ответ не найден", code="answer_not_found")
    log.feedback = 1 if helpful else -1
    log.feedback_comment = (comment or "").strip() or None
    await bus.publish(
        db, AnswerFeedback(qa_id=log.id, handover_id=log.handover_id, user_id=user.id, helpful=helpful)
    )
    await db.commit()
    return to_out(log)


async def history(db: AsyncSession, user: User, handover_id: uuid.UUID) -> list[AnswerOut]:
    await ensure_handover_access(db, user, handover_id, ASKERS)
    rows = (
        await db.execute(
            select(QaLog)
            .where(QaLog.handover_id == handover_id, QaLog.user_id == user.id)
            .order_by(QaLog.created_at.desc())
            .limit(HISTORY_LIMIT)
        )
    ).scalars()
    return [to_out(log) for log in reversed(list(rows))]
