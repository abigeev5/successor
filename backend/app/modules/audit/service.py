import uuid
from typing import Any

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
