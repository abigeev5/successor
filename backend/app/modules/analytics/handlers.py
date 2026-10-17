"""Domain events → rows in `events` (same transaction as the action)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import EventBus
from app.modules.analytics.models import ProductEvent
from app.modules.assistant.events import AnswerFeedback, AnswerRefused, AnswerShown
from app.modules.gaps.events import GapAnswered, GapCreated
from app.modules.interview.events import InterviewSessionFinished, InterviewTurnCompleted
from app.modules.knowledge.events import CardApproved, CardDrafted, CardDropped, CardRejected


def _add(
    db: AsyncSession, name: str, *, user_id: uuid.UUID | None, handover_id: uuid.UUID | None, **props: Any
) -> None:
    db.add(ProductEvent(name=name, user_id=user_id, handover_id=handover_id, props=props))


async def on_turn(db: AsyncSession, e: InterviewTurnCompleted) -> None:
    _add(db, "interview_turn", user_id=e.user_id, handover_id=e.handover_id, step=e.step, voice=e.voice)


async def on_session_finished(db: AsyncSession, e: InterviewSessionFinished) -> None:
    _add(
        db,
        "interview_session_finished",
        user_id=e.user_id,
        handover_id=e.handover_id,
        active_seconds=e.active_seconds,
    )


async def on_card_drafted(db: AsyncSession, e: CardDrafted) -> None:
    _add(
        db, "card_generated", user_id=None, handover_id=e.handover_id, card_id=str(e.card_id), origin=e.origin
    )


async def on_card_dropped(db: AsyncSession, e: CardDropped) -> None:
    _add(db, "card_dropped_no_evidence", user_id=None, handover_id=e.handover_id, origin=e.origin)


async def on_card_approved(db: AsyncSession, e: CardApproved) -> None:
    _add(
        db,
        "card_approved",
        user_id=e.user_id,
        handover_id=e.handover_id,
        card_id=str(e.card_id),
        version=e.version,
        edited=e.edited,
    )


async def on_card_rejected(db: AsyncSession, e: CardRejected) -> None:
    _add(db, "card_rejected", user_id=e.user_id, handover_id=e.handover_id, card_id=str(e.card_id))


async def on_answer_shown(db: AsyncSession, e: AnswerShown) -> None:
    _add(db, "question_asked", user_id=e.user_id, handover_id=e.handover_id, qa_id=str(e.qa_id))
    _add(
        db,
        "answer_shown",
        user_id=e.user_id,
        handover_id=e.handover_id,
        qa_id=str(e.qa_id),
        status=e.status,
        groundedness=e.groundedness,
        latency_ms=e.latency_ms,
    )


async def on_answer_refused(db: AsyncSession, e: AnswerRefused) -> None:
    # The question text stays in qa_logs; events hold numbers and ids only.
    _add(db, "question_asked", user_id=e.user_id, handover_id=e.handover_id, qa_id=str(e.qa_id))
    _add(
        db,
        "answer_shown",
        user_id=e.user_id,
        handover_id=e.handover_id,
        qa_id=str(e.qa_id),
        status="refused",
        groundedness=None,
        latency_ms=e.latency_ms,
    )


async def on_feedback(db: AsyncSession, e: AnswerFeedback) -> None:
    _add(
        db,
        "answer_feedback",
        user_id=e.user_id,
        handover_id=e.handover_id,
        qa_id=str(e.qa_id),
        helpful=e.helpful,
    )


async def on_gap_created(db: AsyncSession, e: GapCreated) -> None:
    _add(
        db,
        "gap_created",
        user_id=e.user_id,
        handover_id=e.handover_id,
        gap_id=str(e.gap_id),
        from_refusal=e.from_refusal,
    )


async def on_gap_answered(db: AsyncSession, e: GapAnswered) -> None:
    _add(db, "gap_answered", user_id=e.user_id, handover_id=e.handover_id, gap_id=str(e.gap_id))


def register(bus: EventBus) -> None:
    bus.subscribe(InterviewTurnCompleted, on_turn)
    bus.subscribe(InterviewSessionFinished, on_session_finished)
    bus.subscribe(CardDrafted, on_card_drafted)
    bus.subscribe(CardDropped, on_card_dropped)
    bus.subscribe(CardApproved, on_card_approved)
    bus.subscribe(CardRejected, on_card_rejected)
    bus.subscribe(AnswerShown, on_answer_shown)
    bus.subscribe(AnswerRefused, on_answer_refused)
    bus.subscribe(AnswerFeedback, on_feedback)
    bus.subscribe(GapCreated, on_gap_created)
    bus.subscribe(GapAnswered, on_gap_answered)
