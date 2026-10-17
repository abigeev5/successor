"""Hybrid search (SPEC 7.8): vector top-k and full-text top-k within a handover, fused by RRF.

Full text uses OR between query words (D-047): `websearch_to_tsquery` requires every word,
so natural questions rarely match at all.
"""

import asyncio
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.search.domain.rrf import group_by_card, rrf
from app.modules.search.models import CardChunk
from app.providers.registry import Providers

# plainto_tsquery stems words and drops stop words; '&' → '|' turns «all words» into «any word».
_FTS = text(
    """
    SELECT c.id, c.card_id, ts_rank_cd(c.tsv, q) AS rank
    FROM card_chunks AS c, CAST(replace(plainto_tsquery('russian', :q)::text, '&', '|') AS tsquery) AS q
    WHERE c.handover_id = :handover_id AND c.tsv @@ q
    ORDER BY rank DESC
    LIMIT :k
    """
)


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: uuid.UUID
    card_id: uuid.UUID
    cosine: float | None  # None: found by full text only
    fts_rank: float | None
    rrf: float


@dataclass
class SearchResult:
    cards: list[uuid.UUID] = field(default_factory=list)  # best first, at most rag_max_cards
    chunks: list[ChunkHit] = field(default_factory=list)  # fused top chunks
    best_cosine: float | None = None
    fts_hits: int = 0

    def log(self) -> dict[str, object]:
        """For qa_logs.retrieval: ids and scores only, no texts."""
        return {
            "best_cosine": self.best_cosine,
            "fts_hits": self.fts_hits,
            "cards": [str(c) for c in self.cards],
            "chunks": [
                {
                    "chunk": str(h.chunk_id),
                    "card": str(h.card_id),
                    "cosine": h.cosine,
                    "fts": h.fts_rank,
                    "rrf": h.rrf,
                }
                for h in self.chunks
            ],
        }


async def search(
    db: AsyncSession, providers: Providers, settings: Settings, handover_id: uuid.UUID, query: str
) -> SearchResult:
    [vector] = await asyncio.to_thread(providers.embeddings.embed, [query])
    distance = CardChunk.embedding.cosine_distance(vector)
    vector_rows = (
        await db.execute(
            select(CardChunk.id, CardChunk.card_id, (1 - distance).label("cosine"))
            .where(CardChunk.handover_id == handover_id)
            .order_by(distance)
            .limit(settings.rag_top_k)
        )
    ).all()

    fts_rows = (
        await db.execute(_FTS, {"q": query, "handover_id": handover_id, "k": settings.rag_top_k})
    ).all()

    cosine = {row.id: float(row.cosine) for row in vector_rows}
    fts = {row.id: float(row.rank) for row in fts_rows}
    card_of = {row.id: row.card_id for row in [*vector_rows, *fts_rows]}
    fused = rrf([[row.id for row in vector_rows], [row.id for row in fts_rows]])[: settings.rag_top_chunks]

    result = SearchResult(
        best_cosine=max(cosine.values()) if cosine else None,
        fts_hits=len(fts_rows),
        chunks=[ChunkHit(cid, card_of[cid], cosine.get(cid), fts.get(cid), score) for cid, score in fused],
    )
    result.cards = group_by_card([h.chunk_id for h in result.chunks], card_of, settings.rag_max_cards)
    return result
