import argparse
import datetime
import logging
from sqlalchemy import select, func, case
from taskforge.db.connection import get_session
from taskforge.task_queue.models import Job, JobStatus, Queue, WorkerRecord, WorkerStatus
from taskforge.task_queue.db import enqueue_single_job
from taskforge.config.logging import setup_logging

# Setup logging when the CLI module is imported
setup_logging()
logger = logging.getLogger(__name__)


def view_dead_letter_queue():
    """Fetches and displays all jobs in the dead-letter queue."""
    logger.info("--- Jobs in Dead-Letter Queue ---", extra={"event": "DeadLetterQueueStart"})
    with get_session() as session:
        stmt = select(Job).where(Job.status == JobStatus.dead).order_by(Job.updated_at.desc())
        dead_jobs = session.execute(stmt).scalars().all()

        if not dead_jobs:
            logger.info("No jobs found in the dead-letter queue.", extra={"event": "DeadLetterQueueEmpty"})
            return

        for job in dead_jobs:
            logger.info(
                "Dead job details",
                extra={
                    "job_id": str(job.id),
                    "job_type": job.type,
                    "attempts": f"{job.attempts}/{job.max_attempts}",
                    "failed_at": job.updated_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
                    "error": job.error_message.strip() if job.error_message else "N/A",
                    "event": "DeadJobDetails"
                }
            )


def view_stats():
    """Display queue statistics: job counts grouped by status."""
    logger.info("--- Queue Statistics ---", extra={"event": "StatsStart"})
    with get_session() as session:
        # Get all queues with job counts by status
        queues = session.execute(select(Queue)).scalars().all()

        if not queues:
            logger.info("No queues found.", extra={"event": "StatsEmpty"})
            return

        for queue in queues:
            # Count jobs by status for this queue
            stmt = (
                select(Job.status, func.count(Job.id))
                .where(Job.queue_id == queue.id)
                .group_by(Job.status)
            )
            status_counts = dict(session.execute(stmt).all())

            total = sum(status_counts.values())
            logger.info(
                f"Queue: {queue.name}",
                extra={
                    "event": "QueueStats",
                    "queue_name": queue.name,
                    "total": total,
                    "pending": status_counts.get(JobStatus.pending, 0),
                    "running": status_counts.get(JobStatus.running, 0),
                    "done": status_counts.get(JobStatus.done, 0),
                    "failed": status_counts.get(JobStatus.failed, 0),
                    "dead": status_counts.get(JobStatus.dead, 0),
                }
            )


def view_history(args):
    """Display job history with optional filtering."""
    logger.info("--- Job History ---", extra={"event": "HistoryStart"})
    with get_session() as session:
        stmt = select(Job).order_by(Job.created_at.desc())

        # Apply filters
        if args.status:
            try:
                status_filter = JobStatus(args.status)
                stmt = stmt.where(Job.status == status_filter)
            except ValueError:
                logger.error(f"Invalid status: {args.status}. Valid: pending, running, done, failed, dead")
                return

        if args.type:
            stmt = stmt.where(Job.type == args.type)

        if args.tag:
            # Filter by tag key=value pairs
            for tag_expr in args.tag:
                key, _, value = tag_expr.partition("=")
                if value:
                    # JSON containment: tags must contain {"key": "value"}
                    stmt = stmt.where(Job.tags[key].as_string() == value)
                else:
                    # Just check if the key exists in tags
                    stmt = stmt.where(Job.tags[key] != None)

        if args.queue:
            stmt = stmt.join(Queue).where(Queue.name == args.queue)

        # Apply limit
        limit = args.limit or 20
        stmt = stmt.limit(limit)

        jobs = session.execute(stmt).scalars().all()

        if not jobs:
            logger.info("No jobs found matching the given filters.", extra={"event": "HistoryEmpty"})
            return

        for job in jobs:
            duration = None
            if job.started_at and job.completed_at:
                duration = f"{(job.completed_at - job.started_at).total_seconds():.2f}s"

            logger.info(
                "Job details",
                extra={
                    "event": "JobHistory",
                    "job_id": str(job.id),
                    "job_type": job.type,
                    "status": job.status.value,
                    "attempts": f"{job.attempts}/{job.max_attempts}",
                    "created_at": job.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if job.created_at else "N/A",
                    "duration": duration or "N/A",
                    "tags": job.tags or {},
                }
            )


def replay_job(args):
    """Re-enqueue a dead job as a new pending job."""
    with get_session() as session:
        job = session.get(Job, args.job_id)

        if not job:
            logger.error(f"Job not found: {args.job_id}", extra={"event": "ReplayNotFound", "job_id": args.job_id})
            return

        if job.status != JobStatus.dead:
            logger.error(
                f"Job {args.job_id} is not dead (status: {job.status.value}). Only dead jobs can be replayed.",
                extra={"event": "ReplayInvalidStatus", "job_id": args.job_id, "status": job.status.value}
            )
            return

        # Get the queue name for re-enqueue
        queue = session.get(Queue, job.queue_id)
        queue_name = queue.name if queue else "default_queue"

    # Enqueue a new job with the same parameters
    new_job = enqueue_single_job(
        job_type=job.type,
        payload=job.payload,
        queue_name=queue_name,
        max_attempts=job.max_attempts,
        tags=job.tags,
    )

    logger.info(
        f"Replayed dead job {args.job_id} as new job {new_job.id}",
        extra={
            "event": "JobReplayed",
            "original_job_id": args.job_id,
            "new_job_id": str(new_job.id),
            "job_type": job.type,
        }
    )


def view_workers():
    """Display registered workers and their status."""
    logger.info("--- Worker Status ---", extra={"event": "WorkersStart"})
    with get_session() as session:
        stmt = select(WorkerRecord).order_by(WorkerRecord.started_at.desc())
        workers = session.execute(stmt).scalars().all()

        if not workers:
            logger.info("No workers registered.", extra={"event": "WorkersEmpty"})
            return

        now = datetime.datetime.now(datetime.UTC)
        for worker in workers:
            # Determine effective status: if online but heartbeat is stale, mark as lost
            effective_status = worker.status.value
            if worker.status == WorkerStatus.online and worker.last_heartbeat_at:
                heartbeat = worker.last_heartbeat_at
                # Ensure both datetimes are tz-aware for comparison
                if heartbeat.tzinfo is None:
                    heartbeat = heartbeat.replace(tzinfo=datetime.UTC)
                seconds_since_heartbeat = (now - heartbeat).total_seconds()
                if seconds_since_heartbeat > 60:
                    effective_status = "lost"

            uptime = None
            if worker.started_at:
                started = worker.started_at
                stopped = worker.stopped_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=datetime.UTC)
                if stopped and stopped.tzinfo is None:
                    stopped = stopped.replace(tzinfo=datetime.UTC)
                end = stopped or now
                uptime = str(end - started).split(".")[0]  # Remove microseconds

            logger.info(
                f"Worker {worker.id[:8]}...",
                extra={
                    "event": "WorkerDetails",
                    "worker_id": worker.id,
                    "hostname": worker.hostname,
                    "pid": worker.pid,
                    "status": effective_status,
                    "queues": worker.queues,
                    "started_at": worker.started_at.strftime('%Y-%m-%d %H:%M:%S UTC') if worker.started_at else "N/A",
                    "last_heartbeat": worker.last_heartbeat_at.strftime('%Y-%m-%d %H:%M:%S UTC') if worker.last_heartbeat_at else "N/A",
                    "uptime": uptime or "N/A",
                }
            )


def main():
    parser = argparse.ArgumentParser(description="TaskForge command-line interface.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command for dead-letter queue
    parser_dead_letter = subparsers.add_parser("dead-letter", help="View jobs in the dead-letter queue.")
    parser_dead_letter.set_defaults(func=lambda args: view_dead_letter_queue())

    # Command for queue statistics
    parser_stats = subparsers.add_parser("stats", help="View queue statistics (job counts by status).")
    parser_stats.set_defaults(func=lambda args: view_stats())

    # Command for job history
    parser_history = subparsers.add_parser("history", help="View job history with optional filters.")
    parser_history.add_argument("--status", type=str, help="Filter by job status (pending, running, done, failed, dead).")
    parser_history.add_argument("--type", type=str, help="Filter by job type.")
    parser_history.add_argument("--tag", type=str, action="append", help="Filter by tag (key=value). Can be repeated.")
    parser_history.add_argument("--queue", type=str, help="Filter by queue name.")
    parser_history.add_argument("--limit", type=int, default=20, help="Maximum number of jobs to display (default: 20).")
    parser_history.set_defaults(func=view_history)

    # Command for replaying dead jobs
    parser_replay = subparsers.add_parser("replay", help="Re-enqueue a dead job as a new pending job.")
    parser_replay.add_argument("job_id", type=str, help="The ID of the dead job to replay.")
    parser_replay.set_defaults(func=replay_job)

    # Command for worker status
    parser_workers = subparsers.add_parser("workers", help="View registered workers and their status.")
    parser_workers.set_defaults(func=lambda args: view_workers())

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
