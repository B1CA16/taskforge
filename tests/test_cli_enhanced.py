import pytest
import logging
import datetime
from taskforge.cli.main import view_stats, view_history, replay_job, view_workers
from taskforge.task_queue.models import Job, JobStatus, Queue, WorkerRecord, WorkerStatus


class MockArgs:
    """Simple mock for argparse args."""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_view_stats_with_queues(db_session, caplog):
    """Test that stats command displays counts per queue."""
    queue = Queue(name="email_queue")
    db_session.add(queue)
    db_session.commit()

    db_session.add(Job(type="send_email", queue_id=queue.id, status=JobStatus.pending))
    db_session.add(Job(type="send_email", queue_id=queue.id, status=JobStatus.pending))
    db_session.add(Job(type="send_email", queue_id=queue.id, status=JobStatus.done))
    db_session.add(Job(type="send_email", queue_id=queue.id, status=JobStatus.dead))
    db_session.commit()

    with caplog.at_level(logging.INFO):
        view_stats()

    # Find the QueueStats record
    stats_record = next(
        (r for r in caplog.records if r.__dict__.get("event") == "QueueStats"),
        None,
    )
    assert stats_record is not None
    assert stats_record.__dict__["queue_name"] == "email_queue"
    assert stats_record.__dict__["pending"] == 2
    assert stats_record.__dict__["done"] == 1
    assert stats_record.__dict__["dead"] == 1
    assert stats_record.__dict__["total"] == 4


def test_view_stats_empty(db_session, caplog):
    """Test that stats command handles empty database."""
    with caplog.at_level(logging.INFO):
        view_stats()

    assert any(
        r.__dict__.get("event") == "StatsEmpty" for r in caplog.records
    )


def test_view_history_all(db_session, caplog):
    """Test that history command displays jobs."""
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    db_session.add(Job(type="task_a", queue_id=queue.id, status=JobStatus.done))
    db_session.add(Job(type="task_b", queue_id=queue.id, status=JobStatus.pending))
    db_session.commit()

    args = MockArgs(status=None, type=None, tag=None, queue=None, limit=20)
    with caplog.at_level(logging.INFO):
        view_history(args)

    history_records = [r for r in caplog.records if r.__dict__.get("event") == "JobHistory"]
    assert len(history_records) == 2


def test_view_history_filter_by_status(db_session, caplog):
    """Test that history command filters by status."""
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    db_session.add(Job(type="task_a", queue_id=queue.id, status=JobStatus.done))
    db_session.add(Job(type="task_b", queue_id=queue.id, status=JobStatus.pending))
    db_session.commit()

    args = MockArgs(status="done", type=None, tag=None, queue=None, limit=20)
    with caplog.at_level(logging.INFO):
        view_history(args)

    history_records = [r for r in caplog.records if r.__dict__.get("event") == "JobHistory"]
    assert len(history_records) == 1
    assert history_records[0].__dict__["status"] == "done"


def test_view_history_filter_by_type(db_session, caplog):
    """Test that history command filters by job type."""
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    db_session.add(Job(type="task_a", queue_id=queue.id))
    db_session.add(Job(type="task_b", queue_id=queue.id))
    db_session.commit()

    args = MockArgs(status=None, type="task_a", tag=None, queue=None, limit=20)
    with caplog.at_level(logging.INFO):
        view_history(args)

    history_records = [r for r in caplog.records if r.__dict__.get("event") == "JobHistory"]
    assert len(history_records) == 1
    assert history_records[0].__dict__["job_type"] == "task_a"


def test_replay_dead_job(db_session, caplog):
    """Test replaying a dead job creates a new pending job."""
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    dead_job = Job(
        type="failing_task",
        payload={"key": "value"},
        queue_id=queue.id,
        status=JobStatus.dead,
        attempts=3,
        max_attempts=3,
        tags={"env": "test"},
    )
    db_session.add(dead_job)
    db_session.commit()

    args = MockArgs(job_id=dead_job.id)
    with caplog.at_level(logging.INFO):
        replay_job(args)

    # Verify a new job was created
    replay_record = next(
        (r for r in caplog.records if r.__dict__.get("event") == "JobReplayed"),
        None,
    )
    assert replay_record is not None
    assert replay_record.__dict__["original_job_id"] == dead_job.id

    # Verify the new job exists in DB
    from sqlalchemy import select
    new_jobs = db_session.execute(
        select(Job).where(Job.status == JobStatus.pending, Job.type == "failing_task")
    ).scalars().all()
    assert len(new_jobs) == 1
    assert new_jobs[0].payload == {"key": "value"}
    assert new_jobs[0].tags == {"env": "test"}


def test_replay_non_dead_job_fails(db_session, caplog):
    """Test that replaying a non-dead job logs an error."""
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    running_job = Job(type="task", queue_id=queue.id, status=JobStatus.running)
    db_session.add(running_job)
    db_session.commit()

    args = MockArgs(job_id=running_job.id)
    with caplog.at_level(logging.ERROR):
        replay_job(args)

    assert any(
        r.__dict__.get("event") == "ReplayInvalidStatus" for r in caplog.records
    )


def test_replay_nonexistent_job_fails(db_session, caplog):
    """Test that replaying a nonexistent job logs an error."""
    args = MockArgs(job_id="nonexistent-id")
    with caplog.at_level(logging.ERROR):
        replay_job(args)

    assert any(
        r.__dict__.get("event") == "ReplayNotFound" for r in caplog.records
    )


def test_view_workers_shows_registered_workers(db_session, caplog):
    """Test that workers command displays registered workers."""
    worker = WorkerRecord(
        id="worker-001",
        hostname="host1",
        pid=1234,
        status=WorkerStatus.online,
        queues=["default_queue"],
        last_heartbeat_at=datetime.datetime.now(datetime.UTC),
    )
    db_session.add(worker)
    db_session.commit()

    with caplog.at_level(logging.INFO):
        view_workers()

    worker_record = next(
        (r for r in caplog.records if r.__dict__.get("event") == "WorkerDetails"),
        None,
    )
    assert worker_record is not None
    assert worker_record.__dict__["worker_id"] == "worker-001"
    assert worker_record.__dict__["hostname"] == "host1"
    assert worker_record.__dict__["status"] == "online"


def test_view_workers_detects_lost_worker(db_session, caplog):
    """Test that a worker with stale heartbeat is shown as lost."""
    stale_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=120)
    worker = WorkerRecord(
        id="worker-002",
        hostname="host1",
        pid=1234,
        status=WorkerStatus.online,
        queues=["default_queue"],
        last_heartbeat_at=stale_time,
    )
    db_session.add(worker)
    db_session.commit()

    with caplog.at_level(logging.INFO):
        view_workers()

    worker_record = next(
        (r for r in caplog.records if r.__dict__.get("event") == "WorkerDetails"),
        None,
    )
    assert worker_record is not None
    assert worker_record.__dict__["status"] == "lost"


def test_view_workers_empty(db_session, caplog):
    """Test that workers command handles no workers."""
    with caplog.at_level(logging.INFO):
        view_workers()

    assert any(
        r.__dict__.get("event") == "WorkersEmpty" for r in caplog.records
    )
