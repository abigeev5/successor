"""Index of approved cards: chunks + embeddings + tsvector. Idempotent: rebuilds the card."""

import asyncio
import logging
import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.handovers.service import get_handover
from app.modules.knowledge.domain.markdown import strip_images
from app.modules.knowledge.models import CardStatus, KnowledgeCard
from app.modules.search.domain.chunking import chunk_card
from app.modules.search.models import EMBEDDING_DIM, CardChunk
from app.providers.registry import Providers

log = logging.getLogger(__name__)


class IndexingError(RuntimeError):
    pass


async def unindex_card(db: AsyncSession, card_id: uuid.UUID) -> None:
    await db.execute(delete(CardChunk).where(CardChunk.card_id == card_id))


async def index_card(db: AsyncSession, providers: Providers, card_id: uuid.UUID) -> int:
    """Replaces the card's chunks. A card that is not approved (any more) is just removed. Returns chunks."""
    await unindex_card(db, card_id)
    card = await db.get(KnowledgeCard, card_id)
    if card is None or card.status is not CardStatus.APPROVED:
        return 0
    handover = await get_handover(db, card.handover_id)
    texts = chunk_card(card.title, card.summary, strip_images(card.body_md), card.applies_when)
    vectors = await asyncio.to_thread(providers.embeddings.embed, texts)
    if any(len(v) != EMBEDDING_DIM for v in vectors):
        raise IndexingError(f"Эмбеддинги должны иметь размерность {EMBEDDING_DIM} (EMBEDDINGS_DIM)")
    for idx, (text, vector) in enumerate(zip(texts, vectors, strict=True)):
        db.add(
            CardChunk(
                card_id=card.id,
                handover_id=card.handover_id,
                org_unit_id=handover.org_unit_id,
                process_id=card.process_id,
                card_version=card.version,
                idx=idx,
                text=text,
                embedding=vector,
                embedding_model=providers.embeddings.model,
            )
        )
    await db.flush()
    log.info("indexed card=%s version=%s chunks=%s", card.id, card.version, len(texts))
    return len(texts)
