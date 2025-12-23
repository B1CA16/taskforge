import time
import uuid
from sqlalchemy import text
from taskforge.db.connection import get_session
from taskforge.task_queue.models import Job, JobStatus
from taskforge.worker.executor import execute_job
import datetime


class Worker:
    def __init__(self, queues=None, max_concurrency=10):
        self.worker_id = str(uuid.uuid4())
        self.queues = queues or ["default_queue"]
        self.max_concurrency = max_concurrency
        self.is_running = False

    def run(self):
        self.is_running = True
        print(f"Worker {self.worker_id} started, polling queues: {self.queues}")
        while self.is_running:
            self._process_job()
            time.sleep(1)  # Poll every second

    def stop(self):
        self.is_running = False
        print(f"Worker {self.worker_id} stopping...")

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
                    return  # No job found

                session.commit()

                # Get the full job object
                job = session.get(Job, job_id)
                if not job:
                    return

                print(f"Worker {self.worker_id} claimed job {job.id}")

                # Execute the job
                job_result, error = execute_job(job)

                # Update job status
                if error:
                    job.status = JobStatus.failed
                    job.error_message = error
                    print(f"Job {job.id} failed")
                else:
                    job.status = JobStatus.done
                    job.result = job_result
                    print(f"Job {job.id} completed successfully")
                
                job.updated_at = datetime.datetime.now(datetime.UTC)
                session.commit()

            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                session.rollback()

