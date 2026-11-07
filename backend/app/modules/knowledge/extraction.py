"""Card extraction from any SourceDocument: windows → LLM → quote validation →
process matching → deduplication → drafts with sources."""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import bus
from app.core.prompts import get_prompts
from app.modules.knowledge.domain.card_types import CardType
from app.modules.knowledge.domain.dedup import find_duplicate
from app.modules.knowledge.domain.quotes import find_quote
from app.modules.knowledge.domain.sources import SourceDocument, SourceFragment
from app.modules.knowledge.domain.windows import make_windows
from app.modules.knowledge.events import CardDrafted, CardDropped
from app.modules.knowledge.models import CardSource, CardStatus, KnowledgeCard
from app.modules.org.domain.matching import match_name
from app.providers.llm.base import Message
from app.providers.registry import Providers

log = logging.getLogger(__name__)
PROMPT = "extract_cards"


class QuoteRef(BaseModel):
    fragment: int
    text: str


class CardCandidate(BaseModel):
    type: CardType
    process_name: str | None = None
    title: str = Field(min_length=1)
    summary: str = ""
    body_md: str = ""
    applies_when: str | None = None
    quotes: list[QuoteRef] = Field(default_factory=list)


class ExtractionOutput(BaseModel):
    cards: list[CardCandidate] = Field(default_factory=list)


@dataclass
class ExtractionResult:
    prompt_version: str
    created: list[uuid.UUID] = field(default_factory=list)
    merged_into: list[uuid.UUID] = field(default_factory=list)
    dropped: int = 0


@dataclass(frozen=True)
class ValidatedSource:
    fragment: SourceFragment
    quote: str


def validate_quotes(candidate: CardCandidate, fragments: list[SourceFragment]) -> list[ValidatedSource]:
    """Keeps quotes that really occur in the referenced fragment (1-based numbers), one per fragment+text."""
    result: list[ValidatedSource] = []
    seen: set[tuple[uuid.UUID, str]] = set()
    for quote in candidate.quotes:
        if not 1 <= quote.fragment <= len(fragments):
            continue
        fragment = fragments[quote.fragment - 1]
        match = find_quote(quote.text, fragment.text)
        if match is None or (fragment.ref.id, match.text) in seen:
            continue
        seen.add((fragment.ref.id, match.text))
        result.append(ValidatedSource(fragment, match.text))
    return result


def _card_text(title: str, summary: str) -> str:
    return f"{title}\n{summary}".strip()


async def _embed(providers: Providers, texts: list[str]) -> list[list[float]]:
    return await asyncio.to_thread(providers.embeddings.embed, texts) if texts else []


async def _add_sources(db: AsyncSession, card_id: uuid.UUID, sources: list[ValidatedSource]) -> None:
    rows = await db.execute(
        select(CardSource.source_id, CardSource.quote).where(CardSource.card_id == card_id)
    )
    existing: set[tuple[uuid.UUID, str]] = {(source_id, quote) for source_id, quote in rows}
    for source in sources:
        key = (source.fragment.ref.id, source.quote)
        if key in existing:
            continue
        existing.add(key)
        db.add(
            CardSource(
                card_id=card_id,
                source_type=source.fragment.ref.type,
                source_id=source.fragment.ref.id,
                quote=source.quote,
                start_ms=source.fragment.start_ms,
                end_ms=source.fragment.end_ms,
            )
        )


async def extract(
    db: AsyncSession,
    providers: Providers,
    doc: SourceDocument,
    processes: list[tuple[uuid.UUID, str]],
    *,
    created_by: uuid.UUID | None = None,
) -> ExtractionResult:
    """Creates draft cards in the caller's transaction (no commit)."""
    prompts = get_prompts()
    result = ExtractionResult(prompt_version=prompts.version(PROMPT))
    if not doc.fragments:
        return result

    existing_cards = list(
        (
            await db.execute(
                select(KnowledgeCard).where(
                    KnowledgeCard.handover_id == doc.handover_id, KnowledgeCard.status != CardStatus.REJECTED
                )
            )
        ).scalars()
    )
    vectors = await _embed(providers, [_card_text(c.title, c.summary) for c in existing_cards])
    known: list[tuple[uuid.UUID, list[float]]] = [
        (c.id, v) for c, v in zip(existing_cards, vectors, strict=True)
    ]
    status_of = {c.id: c.status for c in existing_cards}

    for window in make_windows([len(f.text) for f in doc.fragments]):
        numbered = [
            {"n": i + 1, "text": doc.fragments[i].text, "context": doc.fragments[i].context} for i in window
        ]
        prompt = prompts.render(PROMPT, processes=[name for _, name in processes], fragments=numbered)
        output = await providers.llm.complete_json([Message("user", prompt.text)], ExtractionOutput)

        for candidate in output.cards:
            sources = validate_quotes(candidate, doc.fragments)
            if not sources:
                result.dropped += 1
                await bus.publish(
                    db,
                    CardDropped(handover_id=doc.handover_id, origin=doc.origin.value, reason="no_evidence"),
                )
                continue

            [vector] = await _embed(providers, [_card_text(candidate.title, candidate.summary)])
            duplicate = find_duplicate(vector, known)
            if duplicate is not None and status_of[duplicate[0]] is CardStatus.DRAFT:
                await _add_sources(db, duplicate[0], sources)
                result.merged_into.append(duplicate[0])
                continue

            card = KnowledgeCard(
                handover_id=doc.handover_id,
                process_id=match_name(candidate.process_name, processes),
                type=candidate.type,
                title=candidate.title.strip(),
                summary=candidate.summary.strip(),
                body_md=candidate.body_md.strip(),
                applies_when=(candidate.applies_when or "").strip() or None,
                status=CardStatus.DRAFT,
                origin=doc.origin,
                duplicate_of=duplicate[0] if duplicate else None,
                created_by=created_by,
            )
            db.add(card)
            await db.flush()
            await _add_sources(db, card.id, sources)
            known.append((card.id, vector))
            status_of[card.id] = CardStatus.DRAFT
            result.created.append(card.id)
            await bus.publish(
                db, CardDrafted(card_id=card.id, handover_id=doc.handover_id, origin=doc.origin.value)
            )

    await db.flush()
    log.info(
        "extraction done: handover=%s created=%s merged=%s dropped=%s",
        doc.handover_id,
        len(result.created),
        len(result.merged_into),
        result.dropped,
    )
    return result
