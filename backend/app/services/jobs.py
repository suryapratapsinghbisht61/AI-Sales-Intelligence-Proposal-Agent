from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Job

STALE_AFTER = timedelta(minutes=15)


def enqueue(db: Session, org_id, kind: str, **payload) -> Job:
    job = Job(org_id=org_id, kind=kind, payload={k: str(v) for k, v in payload.items()})
    db.add(job)
    return job


def claim(db: Session) -> Job | None:
    """Claim one due job. Jobs stuck in `running` past STALE_AFTER (crashed worker) are reclaimed."""
    now = datetime.now(UTC)
    job = db.scalar(
        select(Job)
        .where(
            ((Job.status == "queued") & (Job.run_after <= now))
            | ((Job.status == "running") & (Job.locked_at < now - STALE_AFTER))
        )
        .order_by(Job.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job:
        job.status, job.locked_at, job.attempts = "running", now, job.attempts + 1
        db.commit()
    return job


def finish(db: Session, job: Job, error: str | None = None) -> bool:
    """Mark done, or schedule a retry with backoff. Returns True when the job has permanently failed."""
    if error is None:
        job.status = "done"
    elif job.attempts >= job.max_attempts:
        job.status, job.error = "failed", error
    else:
        job.status, job.error = "queued", error
        job.run_after = datetime.now(UTC) + timedelta(seconds=10 * 2**job.attempts)
    db.commit()
    return job.status == "failed"
