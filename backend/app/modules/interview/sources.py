"""Interview as a knowledge source: SourceDocument for extraction and a resolver for the review screen."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.interview.models import InterviewMessage, InterviewSession, MessageRole
from app.modules.knowledge.domain.sources import (
    CardOrigin,
    SourceDocument,
    SourceFragment,
    SourceRef,
    SourceType,
)
from app.modules.knowledge.resolvers import ResolvedSource


async def build_source_document(db: AsyncSession, session: InterviewSession) -> SourceDocument:
    """Expert answers are the fragments; the preceding question is context, not evidence."""
    messages = (
        await db.execute(
            select(InterviewMessage)
            .where(InterviewMessage.session_id == session.id)
            .order_by(InterviewMessage.seq)
        )
    ).scalars()
    fragments: list[SourceFragment] = []
    question: str | None = None
    for message in messages:
        if message.role is MessageRole.INTERVIEWER:
            question = message.content
            continue
        fragments.append(
            SourceFragment(
                ref=SourceRef(SourceType.INTERVIEW_MESSAGE, message.id),
                text=message.content,
                label=f"Реплика {message.seq}",
                context=question,
            )
        )
        question = None
    return SourceDocument(handover_id=session.handover_id, origin=CardOrigin.INTERVIEW, fragments=fragments)


class InterviewMessageResolver:
    source_type = SourceType.INTERVIEW_MESSAGE

    async def resolve(self, db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, ResolvedSource]:
        rows = await db.execute(
            select(InterviewMessage, InterviewSession.started_at)
            .join(InterviewSession, InterviewSession.id == InterviewMessage.session_id)
            .where(InterviewMessage.id.in_(ids))
        )
        return {
            message.id: ResolvedSource(
                label=f"Интервью {started_at:%d.%m.%Y}, реплика {message.seq}",
                context=message.content,
                link={"session_id": str(message.session_id), "seq": str(message.seq)},
            )
            for message, started_at in rows
        }
