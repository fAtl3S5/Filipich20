from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.models.entities import Job, JobStatus


async def enqueue_job(
    session: AsyncSession,
    job_type: str,
    payload: dict[str, Any] | None = None,
    *,
    unique_key: str | None = None,
    run_at: datetime | None = None,
    max_attempts: int = 10,
) -> Job | None:
    payload = payload or {}
    run_at = run_at or utcnow()
    if unique_key:
        # SQLite-compatible upsert-ish: skip if exists
        existing = await session.execute(select(Job).where(Job.unique_key == unique_key))
        if existing.scalar_one_or_none():
            return None
    job = Job(
        job_type=job_type,
        unique_key=unique_key,
        payload=payload,
        run_at=run_at,
        max_attempts=max_attempts,
        status=JobStatus.pending,
    )
    session.add(job)
    await session.flush()
    return job


async def claim_jobs(
    session: AsyncSession,
    *,
    worker_id: str,
    limit: int = 10,
) -> list[Job]:
    now = utcnow()
    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"

    if dialect == "postgresql":
        stmt = (
            select(Job)
            .where(
                Job.status == JobStatus.pending,
                Job.run_at <= now,
            )
            .order_by(Job.run_at)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        result = await session.execute(stmt)
        jobs = list(result.scalars().all())
    else:
        result = await session.execute(
            select(Job)
            .where(Job.status == JobStatus.pending, Job.run_at <= now)
            .order_by(Job.run_at)
            .limit(limit)
        )
        jobs = list(result.scalars().all())

    for job in jobs:
        job.status = JobStatus.running
        job.locked_by = worker_id
        job.locked_at = now
        job.attempts += 1
    await session.flush()
    return jobs


async def complete_job(session: AsyncSession, job: Job) -> None:
    job.status = JobStatus.done
    job.locked_by = None
    job.locked_at = None
    await session.flush()


async def fail_job(
    session: AsyncSession,
    job: Job,
    error: str,
    *,
    retry_delay_sec: int = 30,
) -> None:
    job.last_error = error[:2000]
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.failed
        job.locked_by = None
        job.locked_at = None
    else:
        job.status = JobStatus.pending
        job.run_at = utcnow() + timedelta(seconds=retry_delay_sec * job.attempts)
        job.locked_by = None
        job.locked_at = None
    await session.flush()


async def cancel_jobs_by_prefix(session: AsyncSession, prefix: str) -> int:
    result = await session.execute(
        select(Job).where(
            Job.status.in_([JobStatus.pending, JobStatus.running]),
            Job.unique_key.is_not(None),
            Job.unique_key.like(f"{prefix}%"),
        )
    )
    jobs = list(result.scalars().all())
    for job in jobs:
        job.status = JobStatus.canceled
    await session.flush()
    return len(jobs)


def new_worker_id() -> str:
    return f"w-{uuid.uuid4().hex[:12]}"
