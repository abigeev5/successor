"""Deleting an expert's answers to gaps (SPEC 7.3). The question stays and waits for a new answer."""

import uuid

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.gaps.models import Gap, GapStatus
from app.modules.knowledge.domain.sources import SourceType
from app.modules.privacy.erasure import Erased, ErasedSource


def _answered_by(user_id: uuid.UUID, handover_id: uuid.UUID) -> tuple[ColumnElement[bool], ...]:
    return Gap.handover_id == handover_id, Gap.answered_by == user_id, Gap.answer_text.is_not(None)


class GapAnswersEraser:
    async def describe(
        self, db: AsyncSession, *, user_id: uuid.UUID, handover_id: uuid.UUID
    ) -> dict[str, int]:
        count = await db.scalar(
            select(func.count()).select_from(Gap).where(*_answered_by(user_id, handover_id))
        )
        return {"gap_answers": count or 0}

    async def erase(
        self, db: AsyncSession, settings: Settings, *, user_id: uuid.UUID, handover_id: uuid.UUID
    ) -> Erased:
        gaps = list((await db.execute(select(Gap).where(*_answered_by(user_id, handover_id)))).scalars())
        for gap in gaps:
            # The answer card loses its only source and is archived, so the question is open again.
            gap.answer_text = None
            gap.answered_by = None
            gap.answered_card_id = None
            if gap.status is GapStatus.ANSWERED:
                gap.status = GapStatus.OPEN
                gap.answered_at = None
        return Erased(
            counts={"gap_answers": len(gaps)},
            sources=[ErasedSource(SourceType.GAP_ANSWER.value, gap.id) for gap in gaps],
        )
