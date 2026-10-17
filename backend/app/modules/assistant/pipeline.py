"""Answering a question (SPEC 7.8): search → refuse or answer → verify claims → assemble.

No writes here: the service stores the result, eval calls this directly.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.prompts import get_prompts
from app.modules.assistant.domain.claims import (
    Sentence,
    assemble,
    cited,
    claims,
    mentions_absence,
    parse_answer,
)
from app.modules.assistant.domain.refusal import is_no_answer, refuse_before_llm
from app.modules.assistant.models import AnswerStatus
from app.modules.knowledge.domain.card_types import CARD_TYPE_LABELS, CardType
from app.modules.knowledge.domain.markdown import strip_images
from app.modules.knowledge.models import CardStatus, KnowledgeCard
from app.modules.search.retriever import SearchResult, search
from app.providers.llm.base import LLMError, Message
from app.providers.registry import Providers

log = logging.getLogger(__name__)
ANSWER_PROMPT = "answer"
VERIFY_PROMPT = "verify_claims"
VERIFY_BATCH = 8
DEGRADED_LEAD = "Модель сейчас недоступна, поэтому показываю найденные карточки без пересказа:"


class ClaimVerdict(BaseModel):
    idx: int
    supported: bool
    reason: str = ""


class VerifyOutput(BaseModel):
    results: list[ClaimVerdict] = Field(default_factory=list)


@dataclass(frozen=True)
class Source:
    n: int
    card_id: uuid.UUID
    title: str
    type: str
    text: str

    def public(self) -> dict[str, Any]:
        return {"n": self.n, "card_id": str(self.card_id), "title": self.title, "type": self.type}


@dataclass
class AnswerResult:
    status: AnswerStatus
    answer: str | None
    sources: list[Source]  # only the cited ones
    groundedness: float | None
    verification: str  # verified | partially_removed | not_verified | degraded | none
    refusal_reason: str | None
    retrieval: dict[str, Any]
    latency_ms: int
    prompt_version: str
    model: str
    claims_total: int = 0
    claims_supported: int = 0
    search: SearchResult = field(default_factory=SearchResult)


def _source_text(card: KnowledgeCard) -> str:
    parts = [card.summary, strip_images(card.body_md)]
    if card.applies_when:
        parts.append(f"Когда применять: {card.applies_when}")
    return "\n".join(p.strip() for p in parts if p and p.strip())


async def _load_sources(db: AsyncSession, card_ids: list[uuid.UUID]) -> list[Source]:
    rows = (
        await db.execute(
            select(KnowledgeCard).where(
                KnowledgeCard.id.in_(card_ids), KnowledgeCard.status == CardStatus.APPROVED
            )
        )
    ).scalars()
    by_id = {card.id: card for card in rows}
    cards = [by_id[i] for i in card_ids if i in by_id]
    return [Source(n, c.id, c.title, c.type.value, _source_text(c)) for n, c in enumerate(cards, start=1)]


def degraded_answer(sources: list[Source]) -> str:
    """Without a model: the found cards as excerpts with citations (D-049)."""
    lines = [DEGRADED_LEAD]
    for s in sources:
        summary = s.text.splitlines()[0] if s.text else ""
        lines.append(f"- **{s.title}** — {summary} [{s.n}]")
    return "\n".join(lines)


async def verify(
    providers: Providers, to_check: list[Sentence], sources: dict[int, Source]
) -> dict[int, bool] | None:
    """Claim id → supported. Claims without (valid) citations are unsupported. None if the judge failed."""
    verdicts: dict[int, bool] = {}
    checkable: list[tuple[Sentence, str]] = []
    for claim in to_check:
        texts = [sources[n].text for n in claim.citations if n in sources]
        if not texts or len(texts) != len(claim.citations):
            verdicts[claim.id] = False
        else:
            checkable.append((claim, "\n---\n".join(texts)))
    prompts = get_prompts()
    for start in range(0, len(checkable), VERIFY_BATCH):
        batch = checkable[start : start + VERIFY_BATCH]
        prompt = prompts.render(
            VERIFY_PROMPT,
            claims=[{"idx": i + 1, "text": c.text, "source_text": src} for i, (c, src) in enumerate(batch)],
        )
        try:
            output = await providers.judge_llm.complete_json([Message("user", prompt.text)], VerifyOutput)
        except LLMError as exc:
            log.warning("claim verification failed: %s", exc)
            return None
        by_idx = {r.idx: r.supported for r in output.results}
        for i, (claim, _) in enumerate(batch):
            verdicts[claim.id] = by_idx.get(i + 1, False)  # no verdict = not confirmed
    return verdicts


def _refused(reason: str, retrieval: SearchResult, started: float, version: str, model: str) -> AnswerResult:
    return AnswerResult(
        status=AnswerStatus.REFUSED,
        answer=None,
        sources=[],
        groundedness=None,
        verification="none",
        refusal_reason=reason,
        retrieval=retrieval.log(),
        latency_ms=int((time.monotonic() - started) * 1000),
        prompt_version=version,
        model=model,
        search=retrieval,
    )


async def answer_question(
    db: AsyncSession, providers: Providers, settings: Settings, handover_id: uuid.UUID, question: str
) -> AnswerResult:
    started = time.monotonic()
    prompts = get_prompts()
    version = (
        f"{ANSWER_PROMPT}@{prompts.version(ANSWER_PROMPT)}+{VERIFY_PROMPT}@{prompts.version(VERIFY_PROMPT)}"
    )
    model = providers.llm.model

    retrieval = await search(db, providers, settings, handover_id, question)
    if not retrieval.cards or refuse_before_llm(
        retrieval.best_cosine,
        retrieval.text_coverage,
        settings.rag_min_similarity,
        settings.rag_min_text_coverage,
    ):
        return _refused("no_relevant_sources", retrieval, started, version, model)

    sources = await _load_sources(db, retrieval.cards)
    prompt = prompts.render(
        ANSWER_PROMPT,
        question=question,
        sources=[
            {"n": s.n, "title": s.title, "type_label": CARD_TYPE_LABELS[CardType(s.type)], "text": s.text}
            for s in sources
        ],
    )
    try:
        raw = await providers.llm.complete([Message("user", prompt.text)], temperature=0.1, max_tokens=800)
    except LLMError as exc:
        log.warning("answer generation failed, showing excerpts: %s", exc)
        return AnswerResult(
            status=AnswerStatus.ANSWERED,
            answer=degraded_answer(sources),
            sources=sources,
            groundedness=None,
            verification="degraded",
            refusal_reason=None,
            retrieval=retrieval.log(),
            latency_ms=int((time.monotonic() - started) * 1000),
            prompt_version=version,
            model=model,
            search=retrieval,
        )
    if is_no_answer(raw):
        return _refused("llm_no_answer", retrieval, started, version, model)

    lines = parse_answer(raw)
    to_check = claims(lines)
    if not to_check:
        return _refused("no_claims", retrieval, started, version, model)
    by_n = {s.n: s for s in sources}
    verdicts = await verify(providers, to_check, by_n)
    if verdicts is None:  # the judge failed: keep the answer, mark it as not verified
        supported = {c.id for c in to_check}
        verification, groundedness = "not_verified", None
    else:
        supported = {cid for cid, ok in verdicts.items() if ok}
        verification = "verified" if len(supported) == len(to_check) else "partially_removed"
        groundedness = len(supported) / len(to_check)
    if not supported:
        result = _refused("unsupported", retrieval, started, version, model)
        result.claims_total = len(to_check)
        return result

    numbers = cited(lines, supported)
    partial = len(supported) < len(to_check) or mentions_absence(lines)
    return AnswerResult(
        status=AnswerStatus.PARTIAL if partial else AnswerStatus.ANSWERED,
        answer=assemble(lines, supported),
        sources=[by_n[n] for n in numbers if n in by_n],
        groundedness=groundedness,
        verification=verification,
        refusal_reason=None,
        retrieval=retrieval.log(),
        latency_ms=int((time.monotonic() - started) * 1000),
        prompt_version=version,
        model=model,
        claims_total=len(to_check),
        claims_supported=len(supported),
        search=retrieval,
    )
