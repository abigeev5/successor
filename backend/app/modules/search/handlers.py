"""Index maintenance: approved → (re)index in the worker; rejected / archived → removed at once."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.core.events import EventBus
from app.core.jobs import JobContext
from app.modules.knowledge.events import CardApproved, CardArchived, CardRejected
from app.modules.search.indexer import index_card, unindex_card

INDEX_JOB = "index_card"


async def index_card_job(ctx: JobContext, payload: dict[str, Any]) -> None:
    await index_card(ctx.db, ctx.providers, uuid.UUID(payload["card_id"]))


async def remove_from_index(db: AsyncSession, event: CardRejected | CardArchived) -> None:
    await unindex_card(db, event.card_id)


def register(bus: EventBus) -> None:
    bus.subscribe_job(
        CardApproved,
        INDEX_JOB,
        dedup_key=lambda e: f"{INDEX_JOB}:{e.card_id}:{e.version}",
        payload=lambda e: {"card_id": str(e.card_id)},
    )
    bus.subscribe(CardRejected, remove_from_index)
    bus.subscribe(CardArchived, remove_from_index)
    jobs.register_handler(INDEX_JOB, index_card_job)
