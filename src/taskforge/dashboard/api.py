"""The dashboard's JSON API, mounted under `/api`.

Endpoint docstrings double as descriptions in the interactive docs at `/docs`.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taskforge.admin import AdminError, replay_dead_job
from taskforge.dashboard.dependencies import get_db
from taskforge.dashboard.schemas import (
    JobDetail,
    JobSummary,
    OverviewStats,
    QueueStats,
    WorkerSummary,
)
from taskforge.task_queue.models import Job, JobStatus, Queue, WorkerRecord, WorkerStatus
from taskforge.utils.time import ensure_utc, utcnow

router = APIRouter(prefix="/api", tags=["api"])


def _job_to_summary(job: Job, queue_name: str) -> JobSummary:
    duration = None
    if job.started_at and job.completed_at:
        duration = (job.completed_at - job.started_at).total_seconds()
    return JobSummary(
        id=job.id,
        type=job.type,
        status=job.status.value,
        queue_name=queue_name,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        tags=job.tags,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=duration,
    )


def _worker_to_summary(worker: WorkerRecord) -> WorkerSummary:
    now = utcnow()
    effective_status = worker.status.value
    # A worker killed without shutting down still says "online"; its stale
    # heartbeat is the only sign that it's gone.
    if (
        worker.status == WorkerStatus.online
        and worker.last_heartbeat_at
        and (now - ensure_utc(worker.last_heartbeat_at)).total_seconds() > 60
    ):
        effective_status = "lost"

    uptime = None
    if worker.started_at:
        end = ensure_utc(worker.stopped_at) or now
        uptime = (end - ensure_utc(worker.started_at)).total_seconds()

    return WorkerSummary(
        id=worker.id,
        hostname=worker.hostname,
        pid=worker.pid,
        status=effective_status,
        queues=worker.queues or [],
        started_at=worker.started_at,
        last_heartbeat_at=worker.last_heartbeat_at,
        stopped_at=worker.stopped_at,
        uptime_seconds=uptime,
    )


@router.get("/overview", response_model=OverviewStats)
def get_overview(db: Session = Depends(get_db)):
    """Return job totals, per-queue counts, online workers and the 10 latest failures.

    Workers count as online only if they sent a heartbeat in the last 60 seconds.
    """
    stmt = (
        select(Queue.name, Job.status, func.count(Job.id))
        .join(Queue, Job.queue_id == Queue.id)
        .group_by(Queue.name, Job.status)
    )
    rows = db.execute(stmt).all()

    queue_map: dict[str, QueueStats] = {}
    for queue_name, status, count in rows:
        if queue_name not in queue_map:
            queue_map[queue_name] = QueueStats(name=queue_name)
        qs = queue_map[queue_name]
        setattr(qs, status.value, count)
        qs.total += count

    queues = list(queue_map.values())

    total_jobs = sum(q.total for q in queues)
    total_pending = sum(q.pending for q in queues)
    total_running = sum(q.running for q in queues)
    total_done = sum(q.done for q in queues)
    total_dead = sum(q.dead for q in queues)

    now = utcnow()
    workers_stmt = select(WorkerRecord).where(WorkerRecord.status == WorkerStatus.online)
    online_workers = db.execute(workers_stmt).scalars().all()
    total_workers_online = sum(
        1
        for w in online_workers
        if w.last_heartbeat_at and (now - ensure_utc(w.last_heartbeat_at)).total_seconds() <= 60
    )

    failures_stmt = (
        select(Job, Queue.name)
        .join(Queue, Job.queue_id == Queue.id)
        .where(Job.status.in_([JobStatus.dead, JobStatus.failed]))
        .order_by(Job.updated_at.desc())
        .limit(10)
    )
    recent_failures = [
        _job_to_summary(job, queue_name) for job, queue_name in db.execute(failures_stmt).all()
    ]

    return OverviewStats(
        total_jobs=total_jobs,
        total_pending=total_pending,
        total_running=total_running,
        total_done=total_done,
        total_dead=total_dead,
        total_workers_online=total_workers_online,
        queues=queues,
        recent_failures=recent_failures,
    )


@router.get("/jobs", response_model=list[JobSummary])
def list_jobs(
    status: str | None = None,
    job_type: str | None = None,
    queue: str | None = None,
    tag_key: str | None = None,
    tag_value: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List jobs, newest first, with optional filters and offset pagination.

    `tag_key` alone matches jobs that have that tag; with `tag_value` the tag must
    equal that value. Returns 400 for an unknown `status`.
    """
    stmt = (
        select(Job, Queue.name)
        .join(Queue, Job.queue_id == Queue.id)
        .order_by(Job.created_at.desc())
    )

    if status:
        try:
            status_enum = JobStatus(status)
            stmt = stmt.where(Job.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status!r}") from None

    if job_type:
        stmt = stmt.where(Job.type == job_type)

    if queue:
        stmt = stmt.where(Queue.name == queue)

    if tag_key and tag_value:
        stmt = stmt.where(Job.tags[tag_key].as_string() == tag_value)
    elif tag_key:
        stmt = stmt.where(Job.tags[tag_key].is_not(None))

    stmt = stmt.offset(offset).limit(limit)

    return [_job_to_summary(job, queue_name) for job, queue_name in db.execute(stmt).all()]


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: str, db: Session = Depends(get_db)):
    """Return everything about one job, including payload, result and last error.

    Returns 404 if the job doesn't exist.
    """
    stmt = select(Job, Queue.name).join(Queue, Job.queue_id == Queue.id).where(Job.id == job_id)
    row = db.execute(stmt).first()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    job, queue_name = row
    duration = None
    if job.started_at and job.completed_at:
        duration = (job.completed_at - job.started_at).total_seconds()

    return JobDetail(
        id=job.id,
        type=job.type,
        status=job.status.value,
        queue_name=queue_name,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        tags=job.tags,
        payload=job.payload,
        result=job.result,
        error_message=job.error_message,
        locked_by=job.locked_by,
        locked_at=job.locked_at,
        scheduled_at=job.scheduled_at,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        updated_at=job.updated_at,
        duration_seconds=duration,
    )


@router.post("/jobs/{job_id}/replay", response_model=JobSummary)
def replay_job(job_id: str, db: Session = Depends(get_db)):
    """Re-enqueue a dead job as a new pending job.

    Returns 404 if the job doesn't exist, 400 if it isn't dead, and 409 if it
    was already replayed.
    """
    try:
        replay = replay_dead_job(job_id)
    except AdminError as e:
        status_code = {"not_found": 404, "not_dead": 400, "already_replayed": 409}[e.code]
        raise HTTPException(status_code=status_code, detail=str(e)) from None

    return _job_to_summary(replay.new_job, replay.queue_name)


@router.get("/workers", response_model=list[WorkerSummary])
def list_workers(db: Session = Depends(get_db)):
    """List every registered worker, newest first, including offline and lost ones."""
    stmt = select(WorkerRecord).order_by(WorkerRecord.started_at.desc())
    workers = db.execute(stmt).scalars().all()
    return [_worker_to_summary(w) for w in workers]


@router.get("/queues", response_model=list[QueueStats])
def list_queues(db: Session = Depends(get_db)):
    """List every queue that has jobs, with job counts by status."""
    stmt = (
        select(Queue.name, Job.status, func.count(Job.id))
        .join(Queue, Job.queue_id == Queue.id)
        .group_by(Queue.name, Job.status)
    )
    rows = db.execute(stmt).all()

    queue_map: dict[str, QueueStats] = {}
    for queue_name, status, count in rows:
        if queue_name not in queue_map:
            queue_map[queue_name] = QueueStats(name=queue_name)
        qs = queue_map[queue_name]
        setattr(qs, status.value, count)
        qs.total += count

    return list(queue_map.values())
