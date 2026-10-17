"""Expert review of cards (SPEC 7.7). Only approved cards reach the knowledge base."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFound
from app.core.events import bus
from app.modules import audit
from app.modules.handovers.access import HandoverAccess, HandoverRole, ensure_handover_access
from app.modules.handovers.service import list_processes
from app.modules.identity.models import User
from app.modules.knowledge import resolvers
from app.modules.knowledge.domain.card_types import CardType
from app.modules.knowledge.domain.sources import CardOrigin, SourceType
from app.modules.knowledge.events import CardApproved, CardArchived, CardRejected
from app.modules.knowledge.models import CardRevision, CardSource, CardStatus, KnowledgeCard
from app.modules.knowledge.schemas import CardCreate, CardDetail, CardEdit, CardListItem, SourceOut

READERS = list(HandoverRole)
REVIEWERS = [HandoverRole.EXPERT, HandoverRole.ADMIN]
NOT_FOUND = "Карточка не найдена"
_EDITABLE = ("type", "process_id", "title", "summary", "body_md", "applies_when")


def visible_statuses(role: HandoverRole) -> set[CardStatus]:
    """Successors see approved cards only (SPEC 7.1)."""
    return {CardStatus.APPROVED} if role is HandoverRole.SUCCESSOR else set(CardStatus)


async def load_card(
    db: AsyncSession, user: User, card_id: uuid.UUID, allowed: list[HandoverRole]
) -> tuple[KnowledgeCard, HandoverAccess]:
    card = await db.get(KnowledgeCard, card_id)
    if card is None:
        raise NotFound(NOT_FOUND, code="card_not_found")
    access = await ensure_handover_access(db, user, card.handover_id, allowed)
    if card.status not in visible_statuses(access.role):
        raise NotFound(NOT_FOUND, code="card_not_found")
    return card, access


async def list_cards(
    db: AsyncSession,
    access: HandoverAccess,
    *,
    status: CardStatus | None = None,
    process_id: uuid.UUID | None = None,
    card_type: CardType | None = None,
) -> list[KnowledgeCard]:
    statuses = visible_statuses(access.role)
    if status is not None:
        statuses &= {status}
    stmt = (
        select(KnowledgeCard)
        .where(KnowledgeCard.handover_id == access.handover_id, KnowledgeCard.status.in_(statuses))
        .order_by(KnowledgeCard.created_at)
    )
    if process_id is not None:
        stmt = stmt.where(KnowledgeCard.process_id == process_id)
    if card_type is not None:
        stmt = stmt.where(KnowledgeCard.type == card_type)
    return list((await db.execute(stmt)).scalars())


async def card_detail(db: AsyncSession, card: KnowledgeCard, role: HandoverRole) -> CardDetail:
    rows = list(
        (
            await db.execute(
                select(CardSource).where(CardSource.card_id == card.id).order_by(CardSource.created_at)
            )
        ).scalars()
    )
    ids_by_type: dict[SourceType, list[uuid.UUID]] = defaultdict(list)
    for row in rows:
        ids_by_type[row.source_type].append(row.source_id)
    resolved = {}
    for source_type, ids in ids_by_type.items():
        resolver = resolvers.get(source_type)
        if resolver is not None:
            for source_id, view in (await resolver.resolve(db, ids)).items():
                resolved[(source_type, source_id)] = view
    show_context = role is not HandoverRole.SUCCESSOR
    sources = []
    for row in rows:
        found = resolved.get((row.source_type, row.source_id))
        sources.append(
            SourceOut(
                id=row.id,
                source_type=row.source_type,
                source_id=row.source_id,
                quote=row.quote,
                start_ms=row.start_ms,
                end_ms=row.end_ms,
                label=found.label if found else "Источник удалён",
                context=found.context if found and show_context else None,
                link=found.link if found else None,
                available=found is not None,
            )
        )
    base = CardListItem.model_validate(card).model_dump()
    return CardDetail(
        **base,
        body_md=card.body_md,
        applies_when=card.applies_when,
        archived_reason=card.archived_reason,
        reject_reason=card.reject_reason,
        approved_at=card.approved_at,
        review_seconds=card.review_seconds,
        sources=sources,
    )


async def _check_process(db: AsyncSession, handover_id: uuid.UUID, process_id: uuid.UUID | None) -> None:
    if process_id is not None and process_id not in {p.id for p in await list_processes(db, handover_id)}:
        raise AppError("Процесс не относится к этой передаче дел", code="bad_process")


def _changes(card: KnowledgeCard, edits: CardEdit | None) -> dict[str, object]:
    if edits is None:
        return {}
    data = edits.model_dump(exclude_unset=True)
    return {k: v for k, v in data.items() if k in _EDITABLE and getattr(card, k) != v}


def _snapshot(card: KnowledgeCard, user_id: uuid.UUID) -> CardRevision:
    return CardRevision(
        card_id=card.id,
        version=card.version,
        type=card.type,
        process_id=card.process_id,
        title=card.title,
        summary=card.summary,
        body_md=card.body_md,
        applies_when=card.applies_when,
        edited_by=user_id,
    )


async def _apply_edits(db: AsyncSession, card: KnowledgeCard, changes: dict[str, object], user: User) -> None:
    await _check_process(db, card.handover_id, changes.get("process_id"))  # type: ignore[arg-type]
    db.add(_snapshot(card, user.id))
    for field, value in changes.items():
        setattr(card, field, value)
    card.version += 1


async def edit_card(db: AsyncSession, card: KnowledgeCard, edits: CardEdit, user: User) -> KnowledgeCard:
    if card.status not in (CardStatus.DRAFT, CardStatus.APPROVED):
        raise AppError("Отклонённую или архивную карточку нельзя править", code="card_not_editable")
    changes = _changes(card, edits)
    if not changes:
        return card
    if card.status is CardStatus.DRAFT:
        await _check_process(db, card.handover_id, changes.get("process_id"))  # type: ignore[arg-type]
        for field, value in changes.items():
            setattr(card, field, value)
    else:
        # Editing an approved card creates a new version and re-indexes it (SPEC 7.7).
        await _apply_edits(db, card, changes, user)
        await bus.publish(
            db,
            CardApproved(
                card_id=card.id,
                handover_id=card.handover_id,
                version=card.version,
                origin=card.origin.value,
                edited=True,
                user_id=user.id,
            ),
        )
    await audit.record(db, action="card.edited", entity="card", entity_id=card.id, user_id=user.id)
    await db.commit()
    return card


async def approve(
    db: AsyncSession, card: KnowledgeCard, user: User, edits: CardEdit | None, review_seconds: int
) -> KnowledgeCard:
    if card.status is not CardStatus.DRAFT:
        raise AppError("Подтвердить можно только черновик", code="card_not_draft")
    changes = _changes(card, edits)
    if changes:  # «Подтвердить с правками»: keep the model's version as a revision
        await _apply_edits(db, card, changes, user)
    card.status = CardStatus.APPROVED
    card.approved_by = user.id
    card.approved_at = datetime.now(UTC)
    card.review_seconds += review_seconds
    await bus.publish(
        db,
        CardApproved(
            card_id=card.id,
            handover_id=card.handover_id,
            version=card.version,
            origin=card.origin.value,
            edited=bool(changes),
            user_id=user.id,
        ),
    )
    await audit.record(
        db,
        action="card.approved",
        entity="card",
        entity_id=card.id,
        user_id=user.id,
        meta={"edited": bool(changes)},
    )
    await db.commit()
    return card


async def reject(
    db: AsyncSession, card: KnowledgeCard, user: User, reason: str | None, review_seconds: int
) -> KnowledgeCard:
    if card.status is not CardStatus.DRAFT:
        raise AppError("Отклонить можно только черновик", code="card_not_draft")
    card.status = CardStatus.REJECTED
    card.reject_reason = (reason or "").strip() or None
    card.review_seconds += review_seconds
    await bus.publish(db, CardRejected(card_id=card.id, handover_id=card.handover_id, user_id=user.id))
    await audit.record(db, action="card.rejected", entity="card", entity_id=card.id, user_id=user.id)
    await db.commit()
    return card


async def merge(db: AsyncSession, card: KnowledgeCard, into_id: uuid.UUID, user: User) -> KnowledgeCard:
    """«Объединить с …»: sources move to the target card, this draft is archived."""
    if card.status is not CardStatus.DRAFT:
        raise AppError("Объединять можно только черновик", code="card_not_draft")
    target = await db.get(KnowledgeCard, into_id)
    if (
        target is None
        or target.id == card.id
        or target.handover_id != card.handover_id
        or target.status in (CardStatus.REJECTED, CardStatus.ARCHIVED)
    ):
        raise AppError(
            "Объединить можно только с действующей карточкой этой передачи", code="bad_merge_target"
        )
    target_keys = set(
        (
            await db.execute(
                select(CardSource.source_id, CardSource.quote).where(CardSource.card_id == target.id)
            )
        ).all()
    )
    for source in (await db.execute(select(CardSource).where(CardSource.card_id == card.id))).scalars():
        if (source.source_id, source.quote) in target_keys:
            await db.delete(source)
        else:
            source.card_id = target.id
    card.status = CardStatus.ARCHIVED
    card.archived_reason = "merged"
    card.duplicate_of = target.id
    await db.execute(
        update(KnowledgeCard).where(KnowledgeCard.duplicate_of == card.id).values(duplicate_of=target.id)
    )
    await bus.publish(db, CardArchived(card_id=card.id, handover_id=card.handover_id, reason="merged"))
    await audit.record(
        db,
        action="card.merged",
        entity="card",
        entity_id=card.id,
        user_id=user.id,
        meta={"into": str(target.id)},
    )
    await db.commit()
    return card


async def create_manual(db: AsyncSession, data: CardCreate, user: User) -> KnowledgeCard:
    await ensure_handover_access(db, user, data.handover_id, REVIEWERS)
    await _check_process(db, data.handover_id, data.process_id)
    card = KnowledgeCard(
        handover_id=data.handover_id,
        process_id=data.process_id,
        type=data.type,
        title=data.title.strip(),
        summary=data.summary.strip(),
        body_md=data.body_md.strip(),
        applies_when=(data.applies_when or "").strip() or None,
        status=CardStatus.DRAFT,
        origin=CardOrigin.MANUAL,
        created_by=user.id,
    )
    db.add(card)
    await db.flush()
    await audit.record(db, action="card.created", entity="card", entity_id=card.id, user_id=user.id)
    await db.commit()
    return card
