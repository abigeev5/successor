"""Knowledge reacts to deleted sources (SPEC 7.3, step 3; docs/architecture.md, 6.6)."""

import uuid
from collections import defaultdict

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import EventBus, bus
from app.modules.knowledge.domain.sources import SourceType
from app.modules.knowledge.events import CardArchived
from app.modules.knowledge.models import CardSource, CardStatus, KnowledgeCard
from app.modules.privacy.erasure import SourcesErased

SOURCE_DELETED = "source_deleted"


async def on_sources_erased(db: AsyncSession, e: SourcesErased) -> None:
    """Links to the deleted sources disappear; a card without any source left is archived and unindexed."""
    ids_by_type: dict[SourceType, list[uuid.UUID]] = defaultdict(list)
    for source in e.sources:
        ids_by_type[SourceType(source.source_type)].append(source.source_id)
    matches = or_(
        *(
            and_(CardSource.source_type == source_type, CardSource.source_id.in_(ids))
            for source_type, ids in ids_by_type.items()
        )
    )
    affected = set((await db.execute(select(CardSource.card_id).where(matches))).scalars())
    await db.execute(delete(CardSource).where(matches))
    still_sourced = set(
        (await db.execute(select(CardSource.card_id).where(CardSource.card_id.in_(affected)))).scalars()
    )
    orphans = list(
        (
            await db.execute(
                select(KnowledgeCard).where(
                    KnowledgeCard.id.in_(affected - still_sourced),
                    KnowledgeCard.status != CardStatus.ARCHIVED,
                )
            )
        ).scalars()
    )
    for card in orphans:
        card.status = CardStatus.ARCHIVED
        card.archived_reason = SOURCE_DELETED
        await bus.publish(
            db, CardArchived(card_id=card.id, handover_id=card.handover_id, reason=SOURCE_DELETED)
        )


def register(event_bus: EventBus) -> None:
    event_bus.subscribe(SourcesErased, on_sources_erased)
