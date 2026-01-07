import logging
import time
import uuid
from sqlalchemy import text
from taskforge.db.connection import get_session
from taskforge.task_queue.models import Job, JobStatus
from taskforge.worker.executor import execute_job
import datetime
from taskforge.config.logging import setup_logging

# Setup logging when the worker module is imported
setup_logging()
logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, queues=None, max_concurrency=10):
        self.worker_id = str(uuid.uuid4())
        self.queues = queues or ["default_queue"]
        self.max_concurrency = max_concurrency
        self.is_running = False

    def run(self):
        self.is_running = True
        logger.info(f"Worker started, polling queues: {self.queues}", extra={'worker_id': self.worker_id})
        while self.is_running:
            self._process_job()
            time.sleep(1)  # Poll every second

    def stop(self):
        self.is_running = False
        logger.info(f"Worker stopping...", extra={'worker_id': self.worker_id})

    def _process_job(self):
        with get_session() as session:
            try:
                # Atomically fetch and lock a job
                raw_sql = text("""
                    UPDATE jobs
                    SET status = 'running', locked_by = :worker_id, locked_at = NOW()
                    WHERE id = (
                        SELECT id
                        FROM jobs
                        WHERE status = 'pending' AND queue_id IN (
                            SELECT id FROM queues WHERE name = ANY(:queue_names)
                        )
                        AND (scheduled_at IS NULL OR scheduled_at <= NOW())
                        ORDER BY created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING id;
                """)
                result = session.execute(raw_sql, {"worker_id": self.worker_id, "queue_names": self.queues})
                job_id = result.scalar_one_or_none()

                if not job_id:
                    session.rollback() # Explicitly rollback the transaction if no job was found to lock
                    return  # No job found

                session.commit() # Commit the lock acquisition

                # Get the full job object
                job = session.get(Job, job_id)
                if not job:
                    return

                # Create a logger adapter to add job context to logs
                job_logger_adapter = logging.LoggerAdapter(
                    logger, {'job_id': str(job.id), 'worker_id': self.worker_id, 'job_type': job.type}
                )

                job_logger_adapter.info("Claimed job")

                # Execute the job
                job_result, error = execute_job(job, logger=job_logger_adapter) # Pass the adapter to executor

                # Update job status
                if error:
                    job.attempts += 1
                    job.error_message = error
                    if job.attempts < job.max_attempts:
                        job.status = JobStatus.pending
                        backoff_seconds = 10 * (2 ** job.attempts)
                        job.scheduled_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=backoff_seconds)
                        job_logger_adapter.warning(f"Job failed, will retry in {backoff_seconds} seconds. Attempt {job.attempts} of {job.max_attempts}.")
                    else:
                        job.status = JobStatus.dead
                        job_logger_adapter.error(f"Job failed after {job.attempts} attempts and was moved to dead-letter queue.")
                else:
                    job.status = JobStatus.done
                    job.result = job_result
                    job_logger_adapter.info("Job completed successfully")
                
                job.updated_at = datetime.datetime.now(datetime.UTC)
                session.commit()

            except Exception as e:
                # Use the main logger for worker-level exceptions, as job context might not be available
                logger.error(f"An unexpected error occurred in worker {self.worker_id}: {e}", exc_info=True)
                session.rollback()
