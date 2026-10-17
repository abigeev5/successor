import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import Forbidden, NotFound
from app.core.prompts import get_prompts
from app.modules import audit
from app.modules.privacy.models import Consent

CONSENT_PROMPT = "consent_v1"
CONSENT_REQUIRED = "Сначала примите согласие на запись и обработку рабочих бесед"


@dataclass(frozen=True)
class ConsentText:
    version: str
    text: str
    hash: str


def current_text(settings: Settings) -> ConsentText:
    rendered = get_prompts().render(CONSENT_PROMPT, retention_days=settings.retention_days_raw_media)
    return ConsentText(
        version=rendered.version, text=rendered.text, hash=hashlib.sha256(rendered.text.encode()).hexdigest()
    )


async def active_consent(db: AsyncSession, user_id: uuid.UUID, handover_id: uuid.UUID) -> Consent | None:
    stmt = (
        select(Consent)
        .where(Consent.user_id == user_id, Consent.handover_id == handover_id, Consent.revoked_at.is_(None))
        .order_by(Consent.accepted_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def require_consent(db: AsyncSession, user_id: uuid.UUID, handover_id: uuid.UUID) -> Consent:
    consent = await active_consent(db, user_id, handover_id)
    if consent is None:
        raise Forbidden(CONSENT_REQUIRED, code="consent_required")
    return consent


async def accept(
    db: AsyncSession, settings: Settings, *, user_id: uuid.UUID, handover_id: uuid.UUID, ip: str | None
) -> Consent:
    existing = await active_consent(db, user_id, handover_id)
    text = current_text(settings)
    if existing is not None and existing.text_hash == text.hash:
        return existing
    if existing is not None:  # the text changed: the old consent is replaced by the new one
        existing.revoked_at = datetime.now(UTC)
    consent = Consent(
        user_id=user_id, handover_id=handover_id, text_version=text.version, text_hash=text.hash, ip=ip
    )
    db.add(consent)
    await db.flush()
    await audit.record(
        db,
        action="consent.accepted",
        entity="consent",
        entity_id=consent.id,
        user_id=user_id,
        meta={"handover_id": str(handover_id), "version": text.version},
    )
    await db.commit()
    return consent


async def revoke(db: AsyncSession, *, consent_id: uuid.UUID, user_id: uuid.UUID) -> Consent:
    consent = await db.get(Consent, consent_id)
    if consent is None or consent.user_id != user_id:
        raise NotFound("Согласие не найдено", code="consent_not_found")
    if consent.revoked_at is None:
        consent.revoked_at = datetime.now(UTC)
        await audit.record(
            db, action="consent.revoked", entity="consent", entity_id=consent.id, user_id=user_id
        )
        await db.commit()
    return consent
