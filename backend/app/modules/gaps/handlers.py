"""Gaps react to the assistant and to card review."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import EventBus
from app.modules.assistant.events import AnswerRefused
from app.modules.gaps import service
from app.modules.gaps.erasure import GapAnswersEraser
from app.modules.gaps.models import Gap
from app.modules.knowledge import resolvers
from app.modules.knowledge.domain.sources import SourceType
from app.modules.knowledge.events import CardApproved, CardRejected
from app.modules.knowledge.resolvers import ResolvedSource
from app.modules.privacy import erasure


async def on_refused(db: AsyncSession, e: AnswerRefused) -> None:
    await service.open_gap(
        db, handover_id=e.handover_id, question=e.question, asked_by=e.user_id, qa_log_id=e.qa_id
    )


async def on_card_approved(db: AsyncSession, e: CardApproved) -> None:
    if e.origin == "gap_answer":
        await service.mark_answered(db, e.card_id)


async def on_card_rejected(db: AsyncSession, e: CardRejected) -> None:
    await service.reopen_for_new_answer(db, e.card_id)


class GapAnswerResolver:
    source_type = SourceType.GAP_ANSWER

    async def resolve(self, db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, ResolvedSource]:
        gaps = (await db.execute(select(Gap).where(Gap.id.in_(ids)))).scalars()
        return {
            g.id: ResolvedSource(
                label=f"Ответ эксперта на вопрос преемника «{g.question[:80]}»",
                context=g.answer_text,
                link={"gap_id": str(g.id)},
            )
            for g in gaps
        }


def register(bus: EventBus) -> None:
    bus.subscribe(AnswerRefused, on_refused)
    bus.subscribe(CardApproved, on_card_approved)
    bus.subscribe(CardRejected, on_card_rejected)
    resolvers.register(GapAnswerResolver())
    erasure.register(GapAnswersEraser())
