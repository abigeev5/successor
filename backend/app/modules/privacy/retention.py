"""Raw media retention: videos and voice older than RETENTION_DAYS_RAW_MEDIA are deleted.

Screenshots (already blurred), steps, transcripts and cards stay. The worker enqueues the job every
RETENTION_CHECK_INTERVAL_S; `dedup_key` keeps one job in the queue.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.core.config import Settings
from app.core.jobs import JobContext
from app.core.storage import Asset, AssetKind, erase_file
from app.modules import audit

log = logging.getLogger(__name__)
PURGE_JOB = "purge_raw_media"
RAW_MEDIA = (AssetKind.AUDIO, AssetKind.VIDEO)


async def purge_expired_media(db: AsyncSession, settings: Settings, now: datetime | None = None) -> int:
    """Deletes expired raw media files. Idempotent. No commit."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=settings.retention_days_raw_media)
    stmt = select(Asset).where(
        Asset.kind.in_(RAW_MEDIA), Asset.deleted_at.is_(None), Asset.created_at < cutoff
    )
    deleted = 0
    for asset in (await db.execute(stmt)).scalars():
        if erase_file(settings, asset):
            deleted += 1
    if deleted:
        await audit.record(
            db,
            action="media.purged",
            entity="asset",
            meta={"files": deleted, "retention_days": settings.retention_days_raw_media},
        )
        log.info("purged raw media files: %s", deleted)
    return deleted


async def purge_job(ctx: JobContext, payload: dict[str, Any]) -> None:
    await purge_expired_media(ctx.db, ctx.settings)


async def schedule(db: AsyncSession) -> None:
    await jobs.enqueue(db, PURGE_JOB, dedup_key=PURGE_JOB)


def register() -> None:
    jobs.register_handler(PURGE_JOB, purge_job)
