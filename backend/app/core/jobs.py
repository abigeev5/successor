"""Job queue on the `jobs` table (SELECT ... FOR UPDATE SKIP LOCKED), no Celery/Redis.

Handlers are registered by modules via `register_handler`; the worker process runs them.
A handler must be idempotent: it can run again after a crash or a retry.
"""

import logging
import traceback
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Index, String, Text, func, select, text, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import Settings
from app.core.db import Base, Timestamps, UUIDPk, str_enum

log = logging.getLogger(__name__)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# Partial unique index: one unfinished job per dedup_key.
_UNFINISHED = text("status IN ('queued', 'running')")


class Job(UUIDPk, Timestamps, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_run_after", "status", "run_after"),
        Index("uq_jobs_dedup_key_unfinished", "dedup_key", unique=True, postgresql_where=_UNFINISHED),
    )

    type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[JobStatus] = mapped_column(str_enum(JobStatus, "job_status"), default=JobStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    dedup_key: Mapped[str | None] = mapped_column(String(200))
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@dataclass
class JobContext:
    db: AsyncSession
    settings: Settings
    providers: Any  # app.providers.registry.Providers; Any to keep core independent of provider types


JobHandler = Callable[[JobContext, dict[str, Any]], Awaitable[None]]
_handlers: dict[str, JobHandler] = {}


def register_handler(job_type: str, handler: JobHandler) -> None:
    if job_type in _handlers and _handlers[job_type] is not handler:
        raise ValueError(f"Job handler for {job_type!r} is already registered")
    _handlers[job_type] = handler


def get_handler(job_type: str) -> JobHandler | None:
    return _handlers.get(job_type)


def clear_handlers() -> None:
    """For tests."""
    _handlers.clear()


async def enqueue(
    db: AsyncSession,
    job_type: str,
    payload: dict[str, Any] | None = None,
    *,
    dedup_key: str | None = None,
    run_after: datetime | None = None,
) -> uuid.UUID | None:
    """Adds a job in the caller's transaction. Returns None if an unfinished job with the same key exists."""
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "type": job_type,
        "payload": payload or {},
        "status": JobStatus.QUEUED,
        "attempts": 0,
        "dedup_key": dedup_key,
    }
    if run_after is not None:
        values["run_after"] = run_after
    stmt = insert(Job).values(**values)
    if dedup_key is not None:
        stmt = stmt.on_conflict_do_nothing(index_elements=["dedup_key"], index_where=_UNFINISHED)
    result = await db.execute(stmt.returning(Job.id))
    return result.scalar_one_or_none()


def backoff_delay(attempts: int, base_s: float) -> timedelta:
    """Delay before retry number `attempts` (1-based): base, 2·base, 4·base, ..."""
    return timedelta(seconds=base_s * 2 ** max(attempts - 1, 0))


async def claim_next(db: AsyncSession) -> Job | None:
    stmt = (
        select(Job)
        .where(Job.status == JobStatus.QUEUED, Job.run_after <= func.now())
        .order_by(Job.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None
    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.started_at = datetime.now(UTC)
    await db.commit()
    return job


async def run_one(sessionmaker: async_sessionmaker[AsyncSession], settings: Settings, providers: Any) -> bool:
    """Claims and runs one job. Returns False if the queue is empty."""
    async with sessionmaker() as db:
        job = await claim_next(db)
        if job is None:
            return False
        job_id, job_type, payload, attempts = job.id, job.type, dict(job.payload), job.attempts

    handler = get_handler(job_type)
    error: str | None = None
    if handler is None:
        error = f"Нет обработчика для задачи типа {job_type!r}"
    else:
        try:
            async with sessionmaker() as db:
                await handler(JobContext(db=db, settings=settings, providers=providers), payload)
                await db.commit()
        except Exception:
            error = traceback.format_exc(limit=5)
            log.exception("job failed: id=%s type=%s attempt=%s", job_id, job_type, attempts)

    async with sessionmaker() as db:
        now = datetime.now(UTC)
        if error is None:
            values: dict[str, Any] = {"status": JobStatus.DONE, "finished_at": now, "error": None}
        elif handler is not None and attempts < settings.job_max_attempts:
            values = {
                "status": JobStatus.QUEUED,
                "error": error,
                "run_after": now + backoff_delay(attempts, settings.job_backoff_base_s),
            }
        else:
            values = {"status": JobStatus.FAILED, "error": error, "finished_at": now}
        await db.execute(update(Job).where(Job.id == job_id).values(**values))
        await db.commit()
    return True


async def requeue_stale(db: AsyncSession, older_than: timedelta) -> int:
    """Returns jobs left in `running` by a crashed worker back to the queue."""
    cutoff = datetime.now(UTC) - older_than
    result = await db.execute(
        update(Job)
        .where(Job.status == JobStatus.RUNNING, Job.started_at < cutoff)
        .values(status=JobStatus.QUEUED, run_after=func.now())
        .returning(Job.id)
    )
    count = len(result.all())
    await db.commit()
    return count
