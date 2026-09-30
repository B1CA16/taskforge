import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from taskforge.db.connection import get_session
from taskforge.metrics.collectors import jobs_enqueued_total

from .models import Job, JobStatus, Queue


def _get_or_create_queue(session: Session, queue_name: str) -> Queue:
    queue = session.query(Queue).filter_by(name=queue_name).first()
    if queue:
        return queue
    try:
        # A savepoint, so losing the race only rolls back this INSERT.
        with session.begin_nested():
            queue = Queue(name=queue_name)
            session.add(queue)
        return queue
    except IntegrityError:
        # Another producer created the same queue concurrently; use theirs.
        return session.query(Queue).filter_by(name=queue_name).one()


def enqueue_single_job(
    job_type: str,
    payload: dict | list | None = None,
    queue_name: str = "default_queue",
    max_attempts: int | None = None,
    scheduled_at: datetime.datetime | None = None,
    tags: dict | None = None,
) -> Job:
    """Enqueue a single job into the specified queue.

    The queue is created on first use.

    Args:
        job_type: The type of the job to enqueue, matching a registered job function.
        payload: The dictionary or list of arguments for the job function.
        queue_name: The name of the queue to add the job to.
        max_attempts: The maximum number of times the job can be attempted.
        scheduled_at: Run the job no earlier than this time. Naive datetimes are
            interpreted as UTC.
        tags: Optional key-value metadata for filtering and grouping
            (e.g. {"env": "prod", "team": "billing"}).

    Returns:
        The persisted ``Job``.
    """
    with get_session() as session:
        queue = _get_or_create_queue(session, queue_name)

        job_kwargs = {
            "type": job_type,
            "payload": payload,
            "queue_id": queue.id,
            "status": JobStatus.pending,
        }
        if max_attempts is not None:
            job_kwargs["max_attempts"] = max_attempts
        if scheduled_at is not None:
            job_kwargs["scheduled_at"] = scheduled_at
        if tags is not None:
            job_kwargs["tags"] = tags

        job = Job(**job_kwargs)
        session.add(job)
        session.commit()
        session.refresh(job)

        jobs_enqueued_total.labels(queue=queue_name, job_type=job_type).inc()

        return job
