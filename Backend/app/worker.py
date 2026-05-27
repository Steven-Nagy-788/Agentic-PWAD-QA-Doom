from __future__ import annotations

import asyncio
import logging
import signal
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import TestRun
from app.repositories.run_repository import RunRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("doom_worker")

POLL_INTERVAL_SECONDS = 5
STALE_RUN_TIMEOUT_MINUTES = 30


async def worker_loop() -> None:
    logger.info("Doom QA Worker starting (poll interval=%ds)", POLL_INTERVAL_SECONDS)
    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

    while not shutdown_event.is_set():
        try:
            await poll_and_process()
        except Exception:
            logger.exception("Worker poll cycle failed")
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=POLL_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

    logger.info("Worker shutting down gracefully")


async def poll_and_process() -> None:
    async with SessionLocal() as db:
        settings = get_settings()
        repo = RunRepository(db)

        result = await db.execute(
            select(TestRun)
            .where(TestRun.status.in_(("pending", "queued")))
            .order_by(TestRun.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        run = result.scalar_one_or_none()
        if run is None:
            return

        if run.created_at and run.created_at.replace(tzinfo=UTC) < datetime.now(UTC) - timedelta(
            minutes=STALE_RUN_TIMEOUT_MINUTES
        ):
            logger.warning("Run %s is stale (created %s), marking as failed", run.id, run.created_at)
            await repo.update(
                run,
                status="failed",
                outcome="error",
                error_message="Run was queued but never picked up within the stale timeout.",
                failure_category="infrastructure",
                failure_stage="worker_stale",
                completed_at=datetime.now(UTC),
            )
            await db.commit()
            return

        started_at = datetime.now(UTC)
        await repo.update(run, status="running", started_at=started_at)
        await db.commit()
        run_id = run.id

    logger.info("Worker picked up run %s", run_id)

    try:
        from app.services.run_loop import agent_run_task

        await agent_run_task(run_id)
        logger.info("Run %s completed successfully", run_id)
    except asyncio.CancelledError:
        logger.info("Run %s was cancelled", run_id)
    except Exception:
        logger.exception("Run %s failed with error", run_id)
        async with SessionLocal() as db:
            run = await db.get(TestRun, run_id)
            if run is not None and run.status not in {"completed", "cancelled"}:
                await RunRepository(db).update(
                    run,
                    status="failed",
                    outcome="error",
                    error_message="Worker encountered an unhandled exception.",
                    completed_at=datetime.now(UTC),
                )
                await db.commit()


async def fail_orphaned_queued_runs() -> int:
    async with SessionLocal() as db:
        result = await db.execute(
            select(TestRun).where(TestRun.status.in_(("running",))).order_by(TestRun.created_at)
        )
        now = datetime.now(UTC)
        failed = 0
        for run in result.scalars().all():
            started = run.started_at or run.created_at
            if started and started.replace(tzinfo=UTC) < now - timedelta(minutes=STALE_RUN_TIMEOUT_MINUTES):
                await RunRepository(db).update(
                    run,
                    status="failed",
                    outcome="error",
                    error_message="Run was running but worker process was restarted.",
                    failure_category="infrastructure",
                    failure_stage="worker_restart",
                    completed_at=now,
                )
                await db.commit()
                failed += 1
        return failed


def main() -> None:
    asyncio.run(_main())


async def _main() -> None:
    orphaned = await fail_orphaned_queued_runs()
    if orphaned:
        logger.warning("Marked %d orphaned runs as failed", orphaned)
    await worker_loop()


if __name__ == "__main__":
    main()
