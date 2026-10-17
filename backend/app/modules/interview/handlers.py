"""Interview subscriptions: finishing a session starts card extraction (SPEC 7.4 → 7.5)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core import jobs
from app.core.events import EventBus
from app.core.jobs import JobContext
from app.modules.handovers.service import list_processes
from app.modules.interview.events import InterviewSessionFinished
from app.modules.interview.models import InterviewSession
from app.modules.interview.sources import InterviewMessageResolver, build_source_document
from app.modules.knowledge import resolvers
from app.modules.knowledge.extraction import extract

EXTRACT_JOB = "extract_cards_from_session"


async def extract_cards_from_session(ctx: JobContext, payload: dict[str, Any]) -> None:
    session = await ctx.db.get(InterviewSession, uuid.UUID(payload["session_id"]))
    if session is None or session.extracted_at is not None:  # deleted or already done (D-043)
        return
    document = await build_source_document(ctx.db, session)
    processes = [(p.id, p.name) for p in await list_processes(ctx.db, session.handover_id)]
    await extract(ctx.db, ctx.providers, document, processes, created_by=None)
    session.extracted_at = datetime.now(UTC)


def register(bus: EventBus) -> None:
    bus.subscribe_job(
        InterviewSessionFinished,
        EXTRACT_JOB,
        dedup_key=lambda e: f"{EXTRACT_JOB}:{e.session_id}",
        payload=lambda e: {"session_id": str(e.session_id)},
    )
    jobs.register_handler(EXTRACT_JOB, extract_cards_from_session)
    resolvers.register(InterviewMessageResolver())
