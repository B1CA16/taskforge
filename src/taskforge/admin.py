"""Administrative operations shared by the CLI and the dashboard."""

from dataclasses import dataclass

from taskforge.db.connection import get_session
from taskforge.task_queue.db import enqueue_single_job
from taskforge.task_queue.models import Job, JobStatus, Queue

# Reserved tag keys linking a replayed dead job and its replacement.
REPLAYED_AS_TAG = "taskforge.replayed_as"
REPLAYED_FROM_TAG = "taskforge.replayed_from"


class AdminError(Exception):
    """An administrative action was rejected (see ``code`` for the reason)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class ReplayResult:
    original: Job
    new_job: Job
    queue_name: str


def replay_dead_job(job_id: str, *, force: bool = False) -> ReplayResult:
    """Re-enqueue a dead job as a new pending job.

    The original job stays ``dead`` (for the audit trail) and is tagged with
    the id of its replacement. Replaying it again is refused unless ``force``
    is set, to avoid running the same work twice by accident.

    Raises:
        AdminError: ``not_found``, ``not_dead`` or ``already_replayed``.
    """
    with get_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise AdminError("not_found", f"Job not found: {job_id}")
        if job.status != JobStatus.dead:
            raise AdminError(
                "not_dead",
                f"Only dead jobs can be replayed. Current status: {job.status.value}",
            )
        tags = dict(job.tags or {})
        if tags.get(REPLAYED_AS_TAG) and not force:
            raise AdminError(
                "already_replayed",
                f"Job {job_id} was already replayed as {tags[REPLAYED_AS_TAG]}",
            )

        queue = session.get(Queue, job.queue_id)
        queue_name = queue.name if queue else "default_queue"

        new_tags = {k: v for k, v in tags.items() if k != REPLAYED_AS_TAG}
        new_tags[REPLAYED_FROM_TAG] = job.id
        new_job = enqueue_single_job(
            job_type=job.type,
            payload=job.payload,
            queue_name=queue_name,
            max_attempts=job.max_attempts,
            tags=new_tags,
        )

        # Reassign (not mutate) so SQLAlchemy notices the JSON change.
        job.tags = {**tags, REPLAYED_AS_TAG: new_job.id}
        session.commit()

        return ReplayResult(original=job, new_job=new_job, queue_name=queue_name)
