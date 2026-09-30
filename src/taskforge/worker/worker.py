import datetime
import json
import logging
import os
import platform
import signal
import threading
import time
import traceback
import uuid

from sqlalchemy import func, select, text

from taskforge.db.connection import get_session
from taskforge.metrics.collectors import (
    active_workers,
    job_execution_duration_seconds,
    jobs_processed_total,
    queue_depth,
    worker_info,
)
from taskforge.metrics.server import start_metrics_server
from taskforge.task_queue.models import Job, JobStatus, Queue, WorkerRecord, WorkerStatus
from taskforge.utils.time import utcnow
from taskforge.worker.executor import execute_job

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 15
METRICS_REFRESH_INTERVAL_SECONDS = 10
DEFAULT_POLL_INTERVAL_SECONDS = 1.0

# Atomically claim the oldest runnable job in one round-trip.
# FOR UPDATE SKIP LOCKED makes concurrent workers skip rows another worker is
# claiming instead of blocking on them, so each job is handed to one worker.
# `failed` jobs are waiting for a retry and become runnable at `scheduled_at`.
# Postgres-only: SQLite has no row locks or SKIP LOCKED.
_CLAIM_SQL = text("""
    UPDATE jobs
    SET status = 'running', locked_by = :worker_id, locked_at = NOW(), started_at = NOW()
    WHERE id = (
        SELECT id
        FROM jobs
        WHERE status IN ('pending', 'failed')
          AND queue_id IN (SELECT id FROM queues WHERE name = ANY(:queue_names))
          AND (scheduled_at IS NULL OR scheduled_at <= NOW())
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id
""")


class Worker:
    """Polls one or more queues and executes jobs one at a time.

    Args:
        queues: Queue names to consume from. Defaults to ``["default_queue"]``.
        max_concurrency: Reserved for concurrent execution (not used yet; jobs
            run one at a time).
        metrics_port: Port for the Prometheus exporter. Defaults to
            ``TASKFORGE_METRICS_PORT`` or 9464.
        enable_metrics: Start the Prometheus exporter and queue-depth refresher.
        poll_interval: Seconds to wait before polling again when no job is ready.
        handle_signals: Install SIGINT/SIGTERM (and SIGBREAK on Windows) handlers
            that stop the worker gracefully. Only possible from the main thread.
    """

    def __init__(
        self,
        queues=None,
        max_concurrency=10,
        metrics_port=None,
        enable_metrics=True,
        poll_interval=DEFAULT_POLL_INTERVAL_SECONDS,
        handle_signals=True,
    ):
        self.worker_id = str(uuid.uuid4())
        self.queues = queues or ["default_queue"]
        self.max_concurrency = max_concurrency
        self.poll_interval = poll_interval
        self.is_running = False
        self._stop_event = threading.Event()
        self._heartbeat_thread = None
        self._metrics_thread = None
        self._metrics_port = metrics_port
        self._enable_metrics = enable_metrics
        self._handle_signals = handle_signals
        self._previous_signal_handlers = {}

    # --- lifecycle -----------------------------------------------------------

    def run(self):
        """Run until :meth:`stop` is called or a termination signal arrives.

        The job in progress is always allowed to finish; a second signal
        aborts immediately.
        """
        self.is_running = True
        self._stop_event.clear()
        self._install_signal_handlers()
        self._register()

        try:
            worker_info.info({
                "worker_id": self.worker_id,
                "hostname": platform.node(),
                "pid": str(os.getpid()),
                "queues": ",".join(self.queues),
            })
            for queue_name in self.queues:
                active_workers.labels(queue=queue_name).inc()

            if self._enable_metrics:
                start_metrics_server(self._metrics_port)

            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()

            if self._enable_metrics:
                self._metrics_thread = threading.Thread(target=self._metrics_refresh_loop, daemon=True)
                self._metrics_thread.start()

            logger.info(f"Worker started, polling queues: {self.queues}", extra={"worker_id": self.worker_id})
            while not self._stop_event.is_set():
                processed = self._process_job()
                if not processed:
                    # Only wait when idle; drain a backlog as fast as possible.
                    self._stop_event.wait(self.poll_interval)
        finally:
            self.is_running = False
            self._deregister()
            self._restore_signal_handlers()

    def stop(self):
        """Ask the worker to stop after the job in progress (if any) finishes."""
        self.is_running = False
        self._stop_event.set()
        logger.info("Worker stopping...", extra={"worker_id": self.worker_id})

    def _install_signal_handlers(self):
        if not self._handle_signals or threading.current_thread() is not threading.main_thread():
            return
        names = ["SIGINT", "SIGTERM", "SIGBREAK"]  # SIGBREAK = Ctrl+Break on Windows
        for name in names:
            signum = getattr(signal, name, None)
            if signum is None:
                continue
            try:
                self._previous_signal_handlers[signum] = signal.signal(signum, self._on_signal)
            except (OSError, ValueError):
                pass

    def _restore_signal_handlers(self):
        for signum, handler in self._previous_signal_handlers.items():
            try:
                signal.signal(signum, handler)
            except (OSError, ValueError):
                pass
        self._previous_signal_handlers.clear()

    def _on_signal(self, signum, _frame):
        if self._stop_event.is_set():
            logger.warning("Second stop signal received, exiting immediately.", extra={"worker_id": self.worker_id})
            raise KeyboardInterrupt
        logger.info(
            f"Received {signal.Signals(signum).name}, finishing current job before exiting "
            "(send again to force).",
            extra={"worker_id": self.worker_id},
        )
        self.stop()

    # --- registration, heartbeats, metrics -----------------------------------

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
        try:
            with get_session() as session:
                record = session.get(WorkerRecord, self.worker_id)
                if record:
                    record.status = WorkerStatus.offline
                    record.stopped_at = utcnow()
                    session.commit()
        except Exception as e:
            logger.warning(f"Failed to deregister worker: {e}", extra={"worker_id": self.worker_id})

        for queue_name in self.queues:
            active_workers.labels(queue=queue_name).dec()

        logger.info("Worker deregistered", extra={"worker_id": self.worker_id})

    def _heartbeat_loop(self):
        """Background thread that periodically updates last_heartbeat_at."""
        while not self._stop_event.is_set():
            try:
                with get_session() as session:
                    record = session.get(WorkerRecord, self.worker_id)
                    if record:
                        record.last_heartbeat_at = utcnow()
                        session.commit()
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}", extra={"worker_id": self.worker_id})
            self._stop_event.wait(HEARTBEAT_INTERVAL_SECONDS)

    def _metrics_refresh_loop(self):
        """Background thread that periodically refreshes queue depth gauges."""
        while not self._stop_event.is_set():
            try:
                self._refresh_queue_depth()
            except Exception as e:
                logger.warning(f"Metrics refresh failed: {e}", extra={"worker_id": self.worker_id})
            self._stop_event.wait(METRICS_REFRESH_INTERVAL_SECONDS)

    def _refresh_queue_depth(self):
        """Query the database to update queue depth gauges."""
        with get_session() as session:
            stmt = (
                select(Queue.name, Job.status, func.count(Job.id))
                .join(Queue, Job.queue_id == Queue.id)
                .group_by(Queue.name, Job.status)
            )
            rows = session.execute(stmt).all()
        # Reset first: a (queue, status) pair that no longer has any jobs
        # must drop to 0 instead of keeping its last value.
        queue_depth.clear()
        for queue_name, status, count in rows:
            queue_depth.labels(queue=queue_name, status=status.value).set(count)

    # --- job processing ------------------------------------------------------

    def _process_job(self) -> bool:
        """Claim and run at most one job.

        Returns:
            True if a job was claimed (whatever its outcome), False if none was ready.
        """
        job_id = self._claim_next_job()
        if job_id is None:
            return False
        self._execute_and_record(job_id)
        return True

    def _claim_next_job(self) -> str | None:
        with get_session() as session:
            try:
                result = session.execute(
                    _CLAIM_SQL, {"worker_id": self.worker_id, "queue_names": self.queues}
                )
                job_id = result.scalar_one_or_none()
                session.commit()
                return job_id
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to claim a job: {e}", exc_info=True, extra={"worker_id": self.worker_id})
                return None

    def _execute_and_record(self, job_id: str) -> None:
        with get_session() as session:
            try:
                job = session.get(Job, job_id)
                if job is None:
                    return
                queue_name = job.queue.name if job.queue else "unknown"
                job_logger = logging.LoggerAdapter(
                    logger, {"job_id": str(job.id), "worker_id": self.worker_id, "job_type": job.type}
                )
                job_logger.info("Claimed job")

                start_time = time.monotonic()
                job_result, error = execute_job(job, logger=job_logger)
                duration = time.monotonic() - start_time
                job_execution_duration_seconds.labels(queue=queue_name, job_type=job.type).observe(duration)

                if error is None:
                    error = _json_serialization_error(job_result)

                self._apply_outcome(job, job_result, error, queue_name, job_logger)
                session.commit()
            except Exception:
                session.rollback()
                logger.error(
                    f"Failed to record the outcome of job {job_id}",
                    exc_info=True,
                    extra={"worker_id": self.worker_id, "job_id": job_id},
                )
                self._record_crash(job_id, traceback.format_exc())

    def _apply_outcome(self, job, job_result, error, queue_name, job_logger) -> None:
        """Set status/result/retry fields on ``job`` (the caller commits)."""
        now = utcnow()
        if error:
            job.attempts += 1
            job.error_message = error
            if job.attempts < job.max_attempts:
                job.status = JobStatus.failed
                backoff_seconds = 10 * (2 ** job.attempts)
                job.scheduled_at = now + datetime.timedelta(seconds=backoff_seconds)
                jobs_processed_total.labels(queue=queue_name, job_type=job.type, status="retried").inc()
                job_logger.warning(
                    f"Job failed, will retry in {backoff_seconds} seconds. "
                    f"Attempt {job.attempts} of {job.max_attempts}."
                )
            else:
                job.status = JobStatus.dead
                job.completed_at = now
                jobs_processed_total.labels(queue=queue_name, job_type=job.type, status="dead").inc()
                job_logger.error(
                    f"Job failed after {job.attempts} attempts and was moved to dead-letter queue."
                )
        else:
            job.status = JobStatus.done
            job.result = job_result
            job.completed_at = now
            jobs_processed_total.labels(queue=queue_name, job_type=job.type, status="done").inc()
            job_logger.info("Job completed successfully")
        job.updated_at = now

    def _record_crash(self, job_id: str, error: str) -> None:
        """Best effort: count a failed attempt so the job doesn't stay ``running``.

        Runs in a fresh session because the original one is unusable. If this
        also fails (e.g. the database is down) the job stays ``running`` until
        stale-job reclamation (planned) picks it up.
        """
        try:
            with get_session() as session:
                job = session.get(Job, job_id)
                if job is None or job.status != JobStatus.running or job.locked_by != self.worker_id:
                    return
                queue_name = job.queue.name if job.queue else "unknown"
                job_logger = logging.LoggerAdapter(
                    logger, {"job_id": str(job.id), "worker_id": self.worker_id, "job_type": job.type}
                )
                self._apply_outcome(
                    job, None, f"Worker failed to record the job outcome:\n{error}", queue_name, job_logger
                )
                session.commit()
        except Exception:
            logger.critical(
                f"Job {job_id} is stuck in 'running': could not record its failure",
                exc_info=True,
                extra={"worker_id": self.worker_id, "job_id": job_id},
            )


def _json_serialization_error(value) -> str | None:
    """Return an error message if ``value`` can't be stored in a JSON column."""
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        return f"TypeError: job result is not JSON-serializable: {exc}"
    return None
