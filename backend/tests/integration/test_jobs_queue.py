import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.events import Event, bus
from app.core.jobs import Job, JobContext, JobStatus
from app.modules.org.models import OrgUnit


async def all_jobs(db: AsyncSession) -> list[Job]:
    db.expire_all()
    return list((await db.execute(select(Job).order_by(Job.created_at))).scalars())


async def run_one() -> bool:
    return await jobs.run_one(get_sessionmaker(), get_settings(), providers=None)


async def test_dedup_key_allows_one_unfinished_job(db: AsyncSession) -> None:
    first = await jobs.enqueue(db, "index", {"n": 1}, dedup_key="index:1")
    second = await jobs.enqueue(db, "index", {"n": 2}, dedup_key="index:1")
    await db.commit()
    assert first is not None and second is None

    await db.execute(update(Job).values(status=JobStatus.DONE))
    await db.commit()
    # A finished job does not block a new one with the same key.
    assert await jobs.enqueue(db, "index", {"n": 3}, dedup_key="index:1") is not None


async def test_successful_job_is_done_and_handler_writes_in_its_transaction(db: AsyncSession) -> None:
    async def create_unit(ctx: JobContext, payload: dict[str, Any]) -> None:
        ctx.db.add(OrgUnit(name=payload["name"]))

    jobs.register_handler("create_unit", create_unit)
    await jobs.enqueue(db, "create_unit", {"name": "Из задачи"})
    await db.commit()

    assert await run_one() is True
    assert await run_one() is False  # queue is empty
    [job] = await all_jobs(db)
    assert (job.status, job.attempts, job.error) == (JobStatus.DONE, 1, None)
    assert (await db.execute(select(OrgUnit.name))).scalars().all() == ["Из задачи"]


async def test_failing_job_is_retried_with_backoff_then_failed(db: AsyncSession) -> None:
    async def boom(ctx: JobContext, payload: dict[str, Any]) -> None:
        ctx.db.add(OrgUnit(name="не должно сохраниться"))
        raise RuntimeError("сбой")

    jobs.register_handler("boom", boom)
    await jobs.enqueue(db, "boom")
    await db.commit()

    for attempt in range(1, get_settings().job_max_attempts + 1):
        assert await run_one() is True
        [job] = await all_jobs(db)
        assert job.attempts == attempt
        if attempt < get_settings().job_max_attempts:
            assert job.status is JobStatus.QUEUED
            assert job.run_after > datetime.now(UTC)
            assert await run_one() is False  # not due yet
            await db.execute(update(Job).values(run_after=datetime.now(UTC) - timedelta(seconds=1)))
            await db.commit()

    assert job.status is JobStatus.FAILED
    assert "сбой" in (job.error or "")
    assert (await db.execute(select(OrgUnit))).first() is None  # handler transaction rolled back


async def test_job_without_handler_fails_at_once(db: AsyncSession) -> None:
    await jobs.enqueue(db, "unknown_type")
    await db.commit()
    await run_one()
    [job] = await all_jobs(db)
    assert job.status is JobStatus.FAILED
    assert "Нет обработчика" in (job.error or "")


async def test_stale_running_jobs_are_requeued(db: AsyncSession) -> None:
    await jobs.enqueue(db, "slow")
    await db.commit()
    await db.execute(
        update(Job).values(status=JobStatus.RUNNING, started_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db.commit()
    assert await jobs.requeue_stale(db, timedelta(minutes=30)) == 1
    [job] = await all_jobs(db)
    assert job.status is JobStatus.QUEUED


@dataclass(frozen=True)
class ThingApproved(Event):
    thing_id: uuid.UUID


async def test_event_job_is_written_in_the_publisher_transaction(db: AsyncSession) -> None:
    bus.subscribe_job(ThingApproved, "index_thing", dedup_key=lambda e: f"index_thing:{e.thing_id}")
    thing_id = uuid.uuid4()

    await bus.publish(db, ThingApproved(thing_id))
    await db.rollback()  # publisher failed → no job
    assert await all_jobs(db) == []

    await bus.publish(db, ThingApproved(thing_id))
    await bus.publish(db, ThingApproved(thing_id))  # duplicate is ignored
    await db.commit()
    [job] = await all_jobs(db)
    assert (job.type, job.payload) == ("index_thing", {"thing_id": str(thing_id)})
