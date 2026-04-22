import logging
import os
import platform
import threading
import time
import uuid
from sqlalchemy import text, func, select
from taskforge.db.connection import get_session
from taskforge.task_queue.models import Job, JobStatus, Queue, WorkerRecord, WorkerStatus
from taskforge.worker.executor import execute_job
from taskforge.metrics.collectors import (
    jobs_processed_total,
    job_execution_duration_seconds,
    queue_depth,
    active_workers,
    worker_info,
)
from taskforge.metrics.server import start_metrics_server
import datetime
from taskforge.config.logging import setup_logging

# Setup logging when the worker module is imported
setup_logging()
logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 15
METRICS_REFRESH_INTERVAL_SECONDS = 10


class Worker:
    def __init__(self, queues=None, max_concurrency=10, metrics_port=9090, enable_metrics=True):
        self.worker_id = str(uuid.uuid4())
        self.queues = queues or ["default_queue"]
        self.max_concurrency = max_concurrency
        self.is_running = False
        self._heartbeat_thread = None
        self._metrics_thread = None
        self._metrics_port = metrics_port
        self._enable_metrics = enable_metrics

    def _register(self):
        """Register this worker in the database."""
        with get_session() as session:
            record = WorkerRecord(
                id=self.worker_id,
                hostname=platform.node(),
                pid=os.getpid(),
                status=WorkerStatus.online,
                queues=self.queues,
            )
            session.add(record)
            session.commit()
            logger.info(
                "Worker registered",
                extra={"worker_id": self.worker_id, "hostname": record.hostname, "pid": record.pid},
            )

    def _deregister(self):
        """Mark this worker as offline in the database."""
        with get_session() as session:
            record = session.get(WorkerRecord, self.worker_id)
            if record:
                record.status = WorkerStatus.offline
                record.stopped_at = datetime.datetime.now(datetime.UTC)
                session.commit()

            # Update active workers gauge
            for queue_name in self.queues:
                active_workers.labels(queue=queue_name).dec()

            logger.info("Worker deregistered", extra={"worker_id": self.worker_id})

    def _heartbeat_loop(self):
        """Background thread that periodically updates last_heartbeat_at."""
        while self.is_running:
            try:
                with get_session() as session:
                    record = session.get(WorkerRecord, self.worker_id)
                    if record:
                        record.last_heartbeat_at = datetime.datetime.now(datetime.UTC)
                        session.commit()
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}", extra={"worker_id": self.worker_id})
            time.sleep(HEARTBEAT_INTERVAL_SECONDS)

    def _metrics_refresh_loop(self):
        """Background thread that periodically refreshes queue depth gauges."""
        while self.is_running:
            try:
                self._refresh_queue_depth()
            except Exception as e:
                logger.warning(f"Metrics refresh failed: {e}", extra={"worker_id": self.worker_id})
            time.sleep(METRICS_REFRESH_INTERVAL_SECONDS)

    def _refresh_queue_depth(self):
        """Query the database to update queue depth gauges."""
        with get_session() as session:
            stmt = (
                select(Queue.name, Job.status, func.count(Job.id))
                .join(Queue, Job.queue_id == Queue.id)
                .group_by(Queue.name, Job.status)
            )
            for queue_name, status, count in session.execute(stmt).all():
                queue_depth.labels(queue=queue_name, status=status.value).set(count)

    def run(self):
        self.is_running = True
        self._register()

        # Publish worker info metric
        worker_info.info({
            "worker_id": self.worker_id,
            "hostname": platform.node(),
            "pid": str(os.getpid()),
            "queues": ",".join(self.queues),
        })

        # Update active workers gauge
        for queue_name in self.queues:
            active_workers.labels(queue=queue_name).inc()

        # Start Prometheus metrics server
        if self._enable_metrics:
            start_metrics_server(self._metrics_port)

        # Start heartbeat background thread
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        # Start metrics refresh background thread
        if self._enable_metrics:
            self._metrics_thread = threading.Thread(target=self._metrics_refresh_loop, daemon=True)
            self._metrics_thread.start()

        logger.info(f"Worker started, polling queues: {self.queues}", extra={"worker_id": self.worker_id})
        try:
            while self.is_running:
                self._process_job()
                time.sleep(1)  # Poll every second
        finally:
            self._deregister()

    def stop(self):
        self.is_running = False
        logger.info("Worker stopping...", extra={"worker_id": self.worker_id})

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
                    session.rollback()
                    return  # No job found

                session.commit()  # Commit the lock acquisition

                # Get the full job object
                job = session.get(Job, job_id)
                if not job:
                    return

                # Resolve queue name for metrics labels
                queue_name = job.queue.name if job.queue else "unknown"

                # Mark job start time
                job.started_at = datetime.datetime.now(datetime.UTC)
                session.commit()

                # Create a logger adapter to add job context to logs
                job_logger_adapter = logging.LoggerAdapter(
                    logger, {"job_id": str(job.id), "worker_id": self.worker_id, "job_type": job.type}
                )

                job_logger_adapter.info("Claimed job")

                # Execute the job and measure duration
                start_time = time.monotonic()
                job_result, error = execute_job(job, logger=job_logger_adapter)
                duration = time.monotonic() - start_time

                # Record execution duration
                job_execution_duration_seconds.labels(queue=queue_name, job_type=job.type).observe(duration)

                # Update job status
                now = datetime.datetime.now(datetime.UTC)
                if error:
                    job.attempts += 1
                    job.error_message = error
                    if job.attempts < job.max_attempts:
                        job.status = JobStatus.pending
                        backoff_seconds = 10 * (2 ** job.attempts)
                        job.scheduled_at = now + datetime.timedelta(seconds=backoff_seconds)
                        jobs_processed_total.labels(queue=queue_name, job_type=job.type, status="retried").inc()
                        job_logger_adapter.warning(
                            f"Job failed, will retry in {backoff_seconds} seconds. "
                            f"Attempt {job.attempts} of {job.max_attempts}."
                        )
                    else:
                        job.status = JobStatus.dead
                        job.completed_at = now
                        jobs_processed_total.labels(queue=queue_name, job_type=job.type, status="dead").inc()
                        job_logger_adapter.error(
                            f"Job failed after {job.attempts} attempts and was moved to dead-letter queue."
                        )
                else:
                    job.status = JobStatus.done
                    job.result = job_result
                    job.completed_at = now
                    jobs_processed_total.labels(queue=queue_name, job_type=job.type, status="done").inc()
                    job_logger_adapter.info("Job completed successfully")

                job.updated_at = now
                session.commit()

            except Exception as e:
                logger.error(
                    f"An unexpected error occurred in worker {self.worker_id}: {e}", exc_info=True
                )
                session.rollback()
