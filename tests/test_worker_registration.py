import pytest
import datetime
from taskforge.task_queue.models import WorkerRecord, WorkerStatus


def test_worker_record_creation(db_session):
    """Test that a worker record can be created and persisted."""
    worker = WorkerRecord(
        id="test-worker-001",
        hostname="test-host",
        pid=12345,
        status=WorkerStatus.online,
        queues=["default_queue", "email_queue"],
    )
    db_session.add(worker)
    db_session.commit()
    db_session.refresh(worker)

    assert worker.id == "test-worker-001"
    assert worker.hostname == "test-host"
    assert worker.pid == 12345
    assert worker.status == WorkerStatus.online
    assert worker.queues == ["default_queue", "email_queue"]
    assert worker.started_at is not None
    assert worker.last_heartbeat_at is not None
    assert worker.stopped_at is None


def test_worker_deregistration(db_session):
    """Test that a worker can be marked as offline."""
    worker = WorkerRecord(
        id="test-worker-002",
        hostname="test-host",
        pid=12345,
        status=WorkerStatus.online,
        queues=["default_queue"],
    )
    db_session.add(worker)
    db_session.commit()

    # Deregister
    worker.status = WorkerStatus.offline
    worker.stopped_at = datetime.datetime.now(datetime.UTC)
    db_session.commit()
    db_session.refresh(worker)

    assert worker.status == WorkerStatus.offline
    assert worker.stopped_at is not None


def test_worker_heartbeat_update(db_session):
    """Test that a worker's heartbeat timestamp can be updated."""
    worker = WorkerRecord(
        id="test-worker-003",
        hostname="test-host",
        pid=12345,
        status=WorkerStatus.online,
        queues=["default_queue"],
    )
    db_session.add(worker)
    db_session.commit()

    initial_heartbeat = worker.last_heartbeat_at

    # Simulate heartbeat update
    new_heartbeat = datetime.datetime.now(datetime.UTC)
    worker.last_heartbeat_at = new_heartbeat
    db_session.commit()
    db_session.refresh(worker)

    # SQLite strips timezone info, so compare without tzinfo
    actual = worker.last_heartbeat_at.replace(tzinfo=None)
    expected = new_heartbeat.replace(tzinfo=None)
    assert actual == expected


def test_worker_status_enum_values(db_session):
    """Test all worker status enum values can be persisted."""
    for i, status in enumerate(WorkerStatus):
        worker = WorkerRecord(
            id=f"test-worker-{i}",
            hostname="test-host",
            pid=12345 + i,
            status=status,
            queues=["default_queue"],
        )
        db_session.add(worker)

    db_session.commit()

    from sqlalchemy import select
    all_workers = db_session.execute(select(WorkerRecord)).scalars().all()
    statuses = {w.status for w in all_workers}
    assert statuses == {WorkerStatus.online, WorkerStatus.offline, WorkerStatus.lost}
