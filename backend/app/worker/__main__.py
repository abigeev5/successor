"""Worker process: `python -m app.worker`. Runs jobs from the `jobs` table."""

import asyncio
import logging
import signal
from datetime import timedelta

from app.core import jobs
from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.core.logging import setup_logging
from app.modules.privacy import retention
from app.providers.registry import build_providers
from app.wiring import wire

log = logging.getLogger("app.worker")


async def main() -> None:
    setup_logging()
    settings = get_settings()
    wire()
    providers = build_providers(settings)
    sessionmaker = get_sessionmaker()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async with sessionmaker() as db:
        requeued = await jobs.requeue_stale(db, timedelta(seconds=settings.job_stale_after_s))
    log.info("worker started, requeued stale jobs: %s", requeued)

    next_purge = loop.time()
    while not stop.is_set():
        try:
            if loop.time() >= next_purge:  # raw media retention (SPEC 7.3)
                async with sessionmaker() as db:
                    await retention.schedule(db)
                    await db.commit()
                next_purge = loop.time() + settings.retention_check_interval_s
            processed = await jobs.run_one(sessionmaker, settings, providers)
        except Exception:
            log.exception("worker loop error")
            processed = False
        if not processed:
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_interval_s)
            except TimeoutError:
                pass

    await dispose_engine()
    log.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
