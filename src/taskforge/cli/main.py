import argparse
import logging
from sqlalchemy import select
from taskforge.db.connection import get_session
from taskforge.task_queue.models import Job, JobStatus
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


def main():
    parser = argparse.ArgumentParser(description="TaskForge command-line interface.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command for dead-letter queue
    parser_dead_letter = subparsers.add_parser("dead-letter", help="View jobs in the dead-letter queue.")
    parser_dead_letter.set_defaults(func=view_dead_letter_queue)

    args = parser.parse_args()
    args.func()


if __name__ == "__main__":
    main()
