"""Regression tests for bugs found in the 2026-09 audit (docs/revamp/01-AUDIT.md)."""

import datetime
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from taskforge.dashboard.app import app
from taskforge.jobs.registry import _job_registry, register
from taskforge.metrics.collectors import queue_depth
from taskforge.metrics.server import start_metrics_server
from taskforge.task_queue.models import Job, JobStatus, Queue, WorkerRecord
from taskforge.worker.executor import execute_job
from taskforge.worker.worker import Worker
from tests.conftest import _check_is_test_database


@pytest.fixture(autouse=True)
def clear_registry():
    _job_registry.clear()
    yield
    _job_registry.clear()


def _queue(db_session, name="default_queue"):
    queue = Queue(name=name)
    db_session.add(queue)
    db_session.commit()
    return queue


def _worker(**kwargs):
    return Worker(queues=["default_queue"], enable_metrics=False, handle_signals=False, **kwargs)


# --- Library hygiene (H1, H2) ------------------------------------------------


def test_import_has_no_side_effects(tmp_path):
    """Importing TaskForge needs no DB and leaves the host's logging alone."""
    code = (
        "import logging\n"
        "handler = logging.StreamHandler()\n"
        "logging.getLogger().addHandler(handler)\n"
        "import taskforge, taskforge.worker.worker, taskforge.cli.main, taskforge.dashboard.app\n"
        "assert logging.getLogger().handlers == [handler], logging.getLogger().handlers\n"
    )
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "TASKFORGE_DATABASE_URL")}
    # Run from an empty directory so no .env file can be found.
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_first_session_in_a_fresh_process_does_not_deadlock(tmp_path):
    """The lazy engine/session-factory initialisation must not self-deadlock."""
    code = (
        "from sqlalchemy import text\n"
        "from taskforge.db.connection import get_session\n"
        "with get_session() as s:\n"
        "    assert s.execute(text('select 1')).scalar() == 1\n"
    )
    env = {**os.environ, "TASKFORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'test.db'}"}
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


def test_init_db_is_idempotent_and_keeps_data(db_session):
    from taskforge.cli.main import init_db

    queue = _queue(db_session)
    init_db()
    init_db()
    db_session.expire_all()
    assert db_session.get(Queue, queue.id) is not None


# --- Test safety (B2) ----------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["postgresql://u:p@localhost/production", "postgresql://u:p@localhost/app", "sqlite:///taskforge.db"],
)
def test_suite_refuses_non_test_databases(url):
    with pytest.raises(pytest.UsageError):
        _check_is_test_database(url)


@pytest.mark.parametrize(
    "url", ["postgresql://u:p@localhost/taskforge_test", "sqlite://", "sqlite:///C:/tmp/test.db"]
)
def test_suite_accepts_test_databases(url):
    _check_is_test_database(url)


# --- Worker (B1, B4, B6, B14) --------------------------------------------------


def test_non_json_result_fails_the_job_instead_of_leaving_it_running(db_session):
    register("returns_object")(lambda: object())
    queue = _queue(db_session)
    job = Job(type="returns_object", queue_id=queue.id, max_attempts=1)
    db_session.add(job)
    db_session.commit()

    _worker()._process_job()

    db_session.expire_all()
    job = db_session.get(Job, job.id)
    assert job.status == JobStatus.dead
    assert "not JSON-serializable" in job.error_message


def test_failure_while_recording_outcome_is_counted_as_an_attempt(db_session, monkeypatch):
    register("ok")(lambda: 1)
    queue = _queue(db_session)
    job = Job(type="ok", queue_id=queue.id, max_attempts=3)
    db_session.add(job)
    db_session.commit()

    worker = _worker()
    real_apply = worker._apply_outcome
    calls = {"n": 0}

    def flaky_apply(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database hiccup")
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(worker, "_apply_outcome", flaky_apply)
    worker._process_job()

    db_session.expire_all()
    job = db_session.get(Job, job.id)
    assert job.status == JobStatus.failed
    assert job.attempts == 1
    assert "database hiccup" in job.error_message


def test_process_job_reports_whether_it_found_work(db_session):
    register("ok")(lambda: 1)
    queue = _queue(db_session)
    worker = _worker()
    assert worker._process_job() is False

    db_session.add(Job(type="ok", queue_id=queue.id))
    db_session.commit()
    assert worker._process_job() is True


def test_worker_drains_backlog_without_sleeping_between_jobs(db_session):
    register("ok")(lambda: 1)
    queue = _queue(db_session)
    db_session.add_all([Job(type="ok", queue_id=queue.id) for _ in range(10)])
    db_session.commit()

    # With a 1 s sleep after every job (the old behaviour) this takes 10+ s.
    worker = _worker(poll_interval=5)
    thread = threading.Thread(target=worker.run)
    thread.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        db_session.expire_all()
        remaining = db_session.execute(select(Job).where(Job.status != JobStatus.done)).all()
        if not remaining:
            break
        time.sleep(0.05)
    worker.stop()
    thread.join(timeout=5)
    assert not remaining
    assert not thread.is_alive()


def test_stop_wakes_an_idle_worker_immediately(db_session):
    worker = _worker(poll_interval=30)
    thread = threading.Thread(target=worker.run)
    thread.start()
    time.sleep(0.3)
    started = time.monotonic()
    worker.stop()
    thread.join(timeout=5)
    assert time.monotonic() - started < 2
    db_session.expire_all()
    assert db_session.get(WorkerRecord, worker.worker_id).status.value == "offline"


def test_first_signal_stops_gracefully_second_forces_exit():
    worker = _worker()
    worker._on_signal(signal.SIGTERM, None)
    assert worker._stop_event.is_set()
    with pytest.raises(KeyboardInterrupt):
        worker._on_signal(signal.SIGTERM, None)


def test_retried_job_is_picked_up_again_once_due(db_session):
    calls = []

    @register("flaky")
    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("boom")
        return "ok"

    queue = _queue(db_session)
    job = Job(type="flaky", queue_id=queue.id, max_attempts=3)
    db_session.add(job)
    db_session.commit()

    worker = _worker()
    worker._process_job()
    db_session.expire_all()
    job = db_session.get(Job, job.id)
    assert job.status == JobStatus.failed

    # Make the retry due now; the worker must claim `failed` jobs too.
    job.scheduled_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
    db_session.commit()
    assert worker._process_job() is True
    db_session.expire_all()
    assert db_session.get(Job, job.id).status == JobStatus.done


# --- Timezones (B7) --------------------------------------------------------------


def test_timestamps_round_trip_as_aware_utc(db_session):
    queue = _queue(db_session)
    lisbon_summer = datetime.timezone(datetime.timedelta(hours=1))
    when = datetime.datetime(2026, 7, 1, 13, 0, tzinfo=lisbon_summer)
    job = Job(type="t", queue_id=queue.id, scheduled_at=when)
    db_session.add(job)
    db_session.commit()

    db_session.expire_all()
    loaded = db_session.get(Job, job.id).scheduled_at
    assert loaded.utcoffset() == datetime.timedelta(0)
    assert loaded == when  # same instant: 12:00 UTC


def test_job_scheduled_slightly_in_the_future_is_not_run_early(db_session):
    # The test DB runs in a non-UTC timezone (see docker-compose.yml); with naive
    # timestamps this job would be claimed an hour early.
    register("ok")(lambda: 1)
    queue = _queue(db_session)
    soon = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
    db_session.add(Job(type="ok", queue_id=queue.id, scheduled_at=soon))
    db_session.commit()
    assert _worker()._process_job() is False


# --- Executor & registry (B16, B17) ---------------------------------------------


def test_executor_does_not_mutate_the_payload(db_session):
    register("with_logger")(lambda x, logger=None: x)
    queue = _queue(db_session)
    job = Job(type="with_logger", payload={"x": 1}, queue_id=queue.id)
    execute_job(job, logger=Mock())
    assert job.payload == {"x": 1}


def test_registering_a_different_function_under_a_taken_name_raises():
    def first():
        pass

    def second():
        pass

    register("task")(first)
    register("task")(first)  # same function again: fine
    with pytest.raises(ValueError, match="already registered"):
        register("task")(second)


# --- Metrics (B9, B10) -----------------------------------------------------------


def test_busy_metrics_port_does_not_crash(monkeypatch):
    import taskforge.metrics.server as server

    monkeypatch.setattr(server, "_metrics_server_started", False)
    with socket.socket() as sock:
        sock.bind(("0.0.0.0", 0))
        sock.listen()
        busy_port = sock.getsockname()[1]
        assert start_metrics_server(busy_port) is False


def test_queue_depth_drops_to_zero_when_a_status_empties(db_session):
    register("ok")(lambda: 1)
    queue = _queue(db_session, "depth_queue")
    db_session.add(Job(type="ok", queue_id=queue.id))
    db_session.commit()
    worker = Worker(queues=["depth_queue"], enable_metrics=False, handle_signals=False)

    worker._refresh_queue_depth()
    assert queue_depth.labels(queue="depth_queue", status="pending")._value.get() == 1

    worker._process_job()
    worker._refresh_queue_depth()
    samples = {
        s.labels["status"]: s.value
        for m in queue_depth.collect()
        for s in m.samples
        if s.labels.get("queue") == "depth_queue"
    }
    assert samples.get("pending", 0) == 0
    assert samples["done"] == 1


# --- Dashboard (B12, result schema) ---------------------------------------------


def test_job_detail_accepts_scalar_results(db_session):
    queue = _queue(db_session)
    job = Job(type="add_numbers", queue_id=queue.id, status=JobStatus.done, result=15)
    db_session.add(job)
    db_session.commit()

    response = TestClient(app).get(f"/api/jobs/{job.id}")
    assert response.status_code == 200
    assert response.json()["result"] == 15


def test_api_refuses_to_replay_the_same_job_twice(db_session):
    queue = _queue(db_session)
    job = Job(type="t", queue_id=queue.id, status=JobStatus.dead)
    db_session.add(job)
    db_session.commit()

    client = TestClient(app)
    assert client.post(f"/api/jobs/{job.id}/replay").status_code == 200
    assert client.post(f"/api/jobs/{job.id}/replay").status_code == 409
