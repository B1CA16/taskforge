from taskforge.db.base import engine, SessionLocal
from .models import Job, Queue, JobStatus
from taskforge.db.connection import get_session
import datetime


def enqueue_single_job(
    job_type: str,
    payload: dict | list | None = None,
    queue_name: str = "default_queue",
    max_attempts: int | None = None,
    scheduled_at: datetime.datetime | None = None,
):
    """
    Enqueues a single job into the specified queue.

    Args:
        job_type: The type of the job to enqueue, matching a registered job function.
        payload: The dictionary or list of arguments for the job function.
        queue_name: The name of the queue to add the job to.
        max_attempts: The maximum number of times the job can be retried.
        scheduled_at: A datetime object specifying when the job should be executed.
    """
    with get_session() as session:
        # Ensure the queue exists, create if not
        queue = session.query(Queue).filter_by(name=queue_name).first()
        if not queue:
            queue = Queue(name=queue_name)
            session.add(queue)
            session.commit()
            session.refresh(queue)

        # Create and add the job
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

        job = Job(**job_kwargs)
        session.add(job)
        session.commit()
        session.refresh(job)
        
        return job

