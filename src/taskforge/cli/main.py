"""TaskForge's command-line interface.

Run `python -m taskforge.cli.main --help` for the list of commands. Output is
written through the logging system, so `setup_logging(formatter_type="json")`
makes every line machine-readable.
"""

import argparse
import logging

from sqlalchemy import func, select

from taskforge.admin import AdminError, replay_dead_job
from taskforge.config.logging import setup_logging
from taskforge.db.connection import get_session
from taskforge.task_queue.models import Job, JobStatus, Queue, WorkerRecord, WorkerStatus
from taskforge.utils.time import utcnow

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Create any missing TaskForge tables.

    Safe to run repeatedly: existing tables are never dropped or altered, so it
    won't apply schema changes to tables that already exist.
    """
    from taskforge.db.base import get_engine
    from taskforge.task_queue.models import Base

    Base.metadata.create_all(bind=get_engine())
    logger.info("Database tables are ready", extra={"event": "InitDb"})


def view_dead_letter_queue() -> None:
    """Log every dead job, most recent first, with its attempts and last error."""
    logger.info("--- Jobs in Dead-Letter Queue ---", extra={"event": "DeadLetterQueueStart"})
    with get_session() as session:
        stmt = select(Job).where(Job.status == JobStatus.dead).order_by(Job.updated_at.desc())
        dead_jobs = session.execute(stmt).scalars().all()

        if not dead_jobs:
            logger.info(
                "No jobs found in the dead-letter queue", extra={"event": "DeadLetterQueueEmpty"}
            )
            return

        for job in dead_jobs:
            logger.info(
                "Dead job details",
                extra={
                    "job_id": str(job.id),
                    "job_type": job.type,
                    "attempts": f"{job.attempts}/{job.max_attempts}",
                    "failed_at": job.updated_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "error": job.error_message.strip() if job.error_message else "N/A",
                    "event": "DeadJobDetails",
                },
            )


def view_stats() -> None:
    """Log the number of jobs in each status, for every queue."""
    logger.info("--- Queue Statistics ---", extra={"event": "StatsStart"})
    with get_session() as session:
        queues = session.execute(select(Queue)).scalars().all()

        if not queues:
            logger.info("No queues found.", extra={"event": "StatsEmpty"})
            return

        for queue in queues:
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
                },
            )


def view_history(args: argparse.Namespace) -> None:
    """Log recent jobs, newest first, optionally filtered.

    Args:
        args: Parsed `history` arguments: `status`, `type`, `queue`, `limit`, and
            `tag` (a list of `key=value` or bare `key` filters, all of which must match).
    """
    logger.info("--- Job History ---", extra={"event": "HistoryStart"})
    with get_session() as session:
        stmt = select(Job).order_by(Job.created_at.desc())

        if args.status:
            try:
                status_filter = JobStatus(args.status)
                stmt = stmt.where(Job.status == status_filter)
            except ValueError:
                logger.error(
                    f"Invalid status: {args.status}. Valid: pending, running, done, failed, dead"
                )
                return

        if args.type:
            stmt = stmt.where(Job.type == args.type)

        if args.tag:
            for tag_expr in args.tag:
                key, _, value = tag_expr.partition("=")
                if value:
                    # as_string() extracts the tag as text (`->>` on Postgres), so it
                    # compares against the string typed on the command line.
                    stmt = stmt.where(Job.tags[key].as_string() == value)
                else:
                    stmt = stmt.where(Job.tags[key].is_not(None))

        if args.queue:
            stmt = stmt.join(Queue).where(Queue.name == args.queue)

        limit = args.limit or 20
        stmt = stmt.limit(limit)

        jobs = session.execute(stmt).scalars().all()

        if not jobs:
            logger.info("No jobs found matching the given filters", extra={"event": "HistoryEmpty"})
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
                    "created_at": job.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                    if job.created_at
                    else "N/A",
                    "duration": duration or "N/A",
                    "tags": job.tags or {},
                },
            )


_REPLAY_ERROR_EVENTS = {
    "not_found": "ReplayNotFound",
    "not_dead": "ReplayInvalidStatus",
    "already_replayed": "ReplayAlreadyReplayed",
}


def replay_job(args: argparse.Namespace) -> None:
    """Re-enqueue a dead job as a new pending job.

    Refused if the job isn't dead, or was already replayed (unless `--force`).
    Failures are logged, not raised, since this runs as a CLI command.

    Args:
        args: Parsed `replay` arguments: `job_id` and `force`.
    """
    try:
        replay = replay_dead_job(args.job_id, force=getattr(args, "force", False))
    except AdminError as e:
        logger.error(str(e), extra={"event": _REPLAY_ERROR_EVENTS[e.code], "job_id": args.job_id})
        return

    logger.info(
        f"Replayed dead job {args.job_id} as new job {replay.new_job.id}",
        extra={
            "event": "JobReplayed",
            "original_job_id": args.job_id,
            "new_job_id": str(replay.new_job.id),
            "job_type": replay.new_job.type,
        },
    )


def view_workers() -> None:
    """Log every registered worker, with its status, heartbeat and uptime.

    A worker that claims to be online but hasn't sent a heartbeat in over 60
    seconds is reported as `lost`.
    """
    logger.info("--- Worker Status ---", extra={"event": "WorkersStart"})
    with get_session() as session:
        stmt = select(WorkerRecord).order_by(WorkerRecord.started_at.desc())
        workers = session.execute(stmt).scalars().all()

        if not workers:
            logger.info("No workers registered.", extra={"event": "WorkersEmpty"})
            return

        now = utcnow()
        for worker in workers:
            effective_status = worker.status.value
            if worker.status == WorkerStatus.online and worker.last_heartbeat_at:
                seconds_since_heartbeat = (now - worker.last_heartbeat_at).total_seconds()
                if seconds_since_heartbeat > 60:
                    effective_status = "lost"

            uptime = None
            if worker.started_at:
                end = worker.stopped_at or now
                uptime = str(end - worker.started_at).split(".")[0]  # drop microseconds

            logger.info(
                f"Worker {worker.id[:8]}...",
                extra={
                    "event": "WorkerDetails",
                    "worker_id": worker.id,
                    "hostname": worker.hostname,
                    "pid": worker.pid,
                    "status": effective_status,
                    "queues": worker.queues,
                    "started_at": worker.started_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                    if worker.started_at
                    else "N/A",
                    "last_heartbeat": worker.last_heartbeat_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                    if worker.last_heartbeat_at
                    else "N/A",
                    "uptime": uptime or "N/A",
                },
            )


def main() -> None:
    """Parse the command line and run the chosen command."""
    parser = argparse.ArgumentParser(description="TaskForge command-line interface.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_init_db = subparsers.add_parser(
        "init-db", help="Create the TaskForge tables if they don't exist."
    )
    parser_init_db.set_defaults(func=lambda args: init_db())

    parser_dead_letter = subparsers.add_parser(
        "dead-letter", help="View jobs in the dead-letter queue."
    )
    parser_dead_letter.set_defaults(func=lambda args: view_dead_letter_queue())

    parser_stats = subparsers.add_parser(
        "stats", help="View queue statistics (job counts by status)."
    )
    parser_stats.set_defaults(func=lambda args: view_stats())

    parser_history = subparsers.add_parser(
        "history", help="View job history with optional filters."
    )
    parser_history.add_argument(
        "--status", type=str, help="Filter by job status (pending, running, done, failed, dead)."
    )
    parser_history.add_argument("--type", type=str, help="Filter by job type.")
    parser_history.add_argument(
        "--tag", type=str, action="append", help="Filter by tag (key=value). Can be repeated."
    )
    parser_history.add_argument("--queue", type=str, help="Filter by queue name.")
    parser_history.add_argument(
        "--limit", type=int, default=20, help="Maximum number of jobs to display (default: 20)."
    )
    parser_history.set_defaults(func=view_history)

    parser_replay = subparsers.add_parser(
        "replay", help="Re-enqueue a dead job as a new pending job."
    )
    parser_replay.add_argument("job_id", type=str, help="The ID of the dead job to replay.")
    parser_replay.add_argument(
        "--force", action="store_true", help="Replay even if the job was already replayed."
    )
    parser_replay.set_defaults(func=replay_job)

    parser_workers = subparsers.add_parser(
        "workers", help="View registered workers and their status."
    )
    parser_workers.set_defaults(func=lambda args: view_workers())

    args = parser.parse_args()
    setup_logging()
    args.func(args)


if __name__ == "__main__":
    main()
