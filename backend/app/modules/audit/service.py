import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


async def record(
    db: AsyncSession,
    *,
    action: str,
    entity: str,
    entity_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Adds an audit entry to the caller's transaction (no commit here)."""
    db.add(AuditLog(action=action, entity=entity, entity_id=entity_id, user_id=user_id, meta=meta or {}))


async def record_once(
    db: AsyncSession,
    *,
    action: str,
    entity: str,
    entity_id: uuid.UUID,
    user_id: uuid.UUID,
    within: timedelta,
    meta: dict[str, Any] | None = None,
) -> bool:
    """Like `record`, but skips a repeat by the same user within `within` (e.g. video seeks). No commit."""
    since = datetime.now(UTC) - within
    recent = await db.scalar(
        select(AuditLog.id)
        .where(
            AuditLog.action == action,
            AuditLog.entity_id == entity_id,
            AuditLog.user_id == user_id,
            AuditLog.at >= since,
        )
        .limit(1)
    )
    if recent is not None:
        return False
    await record(db, action=action, entity=entity, entity_id=entity_id, user_id=user_id, meta=meta)
    return True
