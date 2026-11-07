"""Deleting an expert's interviews: sessions, messages and voice files are removed for good."""

import uuid
from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.storage import Asset, erase_file
from app.modules.interview.models import InterviewMessage, InterviewSession
from app.modules.knowledge.domain.sources import SourceType
from app.modules.privacy.erasure import Erased, ErasedSource


def _sessions(user_id: uuid.UUID, handover_id: uuid.UUID) -> Select[Any]:
    return select(InterviewSession.id).where(
        InterviewSession.handover_id == handover_id, InterviewSession.expert_id == user_id
    )


class InterviewEraser:
    async def describe(
        self, db: AsyncSession, *, user_id: uuid.UUID, handover_id: uuid.UUID
    ) -> dict[str, int]:
        count = await db.scalar(
            select(func.count())
            .select_from(InterviewMessage)
            .where(InterviewMessage.session_id.in_(_sessions(user_id, handover_id)))
        )
        return {"interview_messages": count or 0}

    async def erase(
        self, db: AsyncSession, settings: Settings, *, user_id: uuid.UUID, handover_id: uuid.UUID
    ) -> Erased:
        messages = (
            await db.execute(
                select(InterviewMessage.id, InterviewMessage.audio_asset_id).where(
                    InterviewMessage.session_id.in_(_sessions(user_id, handover_id))
                )
            )
        ).all()
        audio_ids = [audio_id for _, audio_id in messages if audio_id is not None]
        files = 0
        for asset in (await db.execute(select(Asset).where(Asset.id.in_(audio_ids)))).scalars():
            if erase_file(settings, asset):
                files += 1
        # Messages go with their sessions (ON DELETE CASCADE); a queued extraction finds no session.
        await db.execute(
            delete(InterviewSession).where(InterviewSession.id.in_(_sessions(user_id, handover_id)))
        )
        return Erased(
            counts={"interview_messages": len(messages)},
            sources=[
                ErasedSource(SourceType.INTERVIEW_MESSAGE.value, message_id) for message_id, _ in messages
            ],
            files=files,
        )
