import pytest
from unittest.mock import Mock
import datetime
import time
from taskforge.jobs.registry import register, get_job_func, _job_registry
from taskforge.worker.executor import execute_job
from taskforge.worker.worker import Worker
from taskforge.task_queue.models import Job, JobStatus, Queue


# Sample functions to be used as jobs
def success_job(x, y):
    return x + y


# New sample job function that accepts a logger
def success_job_with_logger(x, y, logger=None):
    if logger:
        logger.info(f"Adding {x} and {y} with logger. Result: {x+y}")
    return x + y


def failure_job():
    raise ValueError("This job intentionally fails")


@pytest.fixture(autouse=True)
def clear_registry():
    """Clears the job registry before each test."""
    _job_registry.clear()
    yield
    _job_registry.clear()


# --- Registry Tests ---


def test_register_job():
    register("success")(success_job)
    assert "success" in _job_registry
    assert _job_registry["success"] == success_job


def test_get_job_func():
    register("success")(success_job)
    func = get_job_func("success")
    assert func == success_job


def test_get_unregistered_job_func():
    with pytest.raises(
        ValueError, match="No job function registered for type: unregistered"
    ):
        get_job_func("unregistered")


# --- Executor Tests ---


def test_execute_successful_job(db_session):
    register("success")(success_job)
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    job = Job(type="success", payload=[2, 3], queue_id=queue.id)
    result, error = execute_job(job, logger=Mock())

    assert error is None
    assert result == 5


def test_execute_failing_job(db_session):
    register("failure")(failure_job)
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    job = Job(type="failure", queue_id=queue.id)
    result, error = execute_job(job, logger=Mock())

    assert result is None
    assert "ValueError: This job intentionally fails" in error


def test_job_function_receives_logger(db_session):
    """
    Verify that a job function that accepts a 'logger' argument receives it.
    """
    mock_logger = Mock()
    register("success_with_logger")(success_job_with_logger)
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    job = Job(type="success_with_logger", payload={"x": 5, "y": 10}, queue_id=queue.id)
    result, error = execute_job(job, logger=mock_logger)

    assert error is None
    assert result == 15
    mock_logger.info.assert_called_once_with("Adding 5 and 10 with logger. Result: 15")


def test_execute_job_with_mismatched_payload(db_session):
    """
    Test that executing a job with a payload that doesn't match the
    function's signature results in a graceful failure.
    """
    register("success")(success_job)
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    # Payload with too many arguments for the function
    job = Job(type="success", payload=[1, 2, 3], queue_id=queue.id)
    result, error = execute_job(job, logger=Mock())

    assert result is None
    assert "TypeError" in error
    assert "takes 2 positional arguments but 3 were given" in error


def test_execute_job_with_unsupported_payload_type(db_session):
    """
    Test that the executor raises a TypeError for unsupported payload types.
    """
    register("success")(success_job)
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    # A string is not a supported payload type
    job = Job(type="success", payload="invalid_payload", queue_id=queue.id)
    result, error = execute_job(job, logger=Mock())

    assert result is None
    assert "TypeError: Unsupported payload type: <class 'str'>" in error


# --- Worker Tests ---


def test_worker_claims_job(db_session):
    register("process_data")(success_job)
    queue = Queue(name="default_queue")
    db_session.add(queue)
    db_session.commit()
    job = Job(type="process_data", payload={"x": 2, "y": 3}, queue_id=queue.id)
    db_session.add(job)
    db_session.commit()

    worker = Worker(queues=["default_queue"], enable_metrics=False)
    worker._process_job()

    db_session.expire_all()
    processed_job = db_session.get(Job, job.id)
    assert processed_job.status == JobStatus.done
    assert processed_job.locked_by == worker.worker_id
    assert processed_job.result == 5


def test_worker_handles_failed_job_and_moves_to_dead(db_session):
    register("failing_task")(failure_job)
    queue = Queue(name="default_queue")
    db_session.add(queue)
    db_session.commit()
    job = Job(type="failing_task", queue_id=queue.id, max_attempts=1)
    db_session.add(job)
    db_session.commit()

    worker = Worker(queues=["default_queue"], enable_metrics=False)
    worker._process_job()

    db_session.expire_all()
    processed_job = db_session.get(Job, job.id)
    assert processed_job.status == JobStatus.dead
    assert processed_job.locked_by == worker.worker_id
    assert "ValueError: This job intentionally fails" in processed_job.error_message


def test_worker_retries_job_with_backoff(db_session):
    register("failing_task")(failure_job)
    queue = Queue(name="default_queue")
    db_session.add(queue)
    db_session.commit()
    job = Job(type="failing_task", queue_id=queue.id, max_attempts=3)
    db_session.add(job)
    db_session.commit()

    worker = Worker(queues=["default_queue"], enable_metrics=False)
    worker._process_job()

    db_session.expire_all()
    processed_job = db_session.get(Job, job.id)
    assert processed_job.status == JobStatus.failed  # waiting for its retry
    assert processed_job.attempts == 1
    assert processed_job.scheduled_at is not None
    # 10 * (2**1) = 20 seconds
    expected_delay = 20
    actual_delay = (processed_job.scheduled_at - processed_job.updated_at).total_seconds()
    # Allow for a small tolerance in timing
    assert actual_delay == pytest.approx(expected_delay, abs=1)


def test_worker_moves_job_to_dead_state_after_retries(db_session):
    register("failing_task")(failure_job)
    queue = Queue(name="default_queue")
    db_session.add(queue)
    db_session.commit()
    # Job has already failed twice
    job = Job(type="failing_task", queue_id=queue.id, attempts=2, max_attempts=3)
    db_session.add(job)
    db_session.commit()

    worker = Worker(queues=["default_queue"], enable_metrics=False)
    worker._process_job()

    db_session.expire_all()
    processed_job = db_session.get(Job, job.id)
    assert processed_job.status == JobStatus.dead
    assert processed_job.attempts == 3


def test_worker_respects_scheduled_at_future(db_session):
    """
    Test that the worker does not pick up a job scheduled for the future.
    """
    register("success")(success_job)
    queue = Queue(name="default_queue")
    db_session.add(queue)
    db_session.commit()

    # Schedule a job to run in one hour
    future_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    job = Job(type="success", queue_id=queue.id, scheduled_at=future_time)
    db_session.add(job)
    db_session.commit()

    # Run a processing cycle
    worker = Worker(queues=["default_queue"], enable_metrics=False)
    worker._process_job()

    # The job should remain pending and not be locked
    db_session.expire_all()
    processed_job = db_session.get(Job, job.id)
    assert processed_job.status == JobStatus.pending
    assert processed_job.locked_by is None


def test_worker_picks_up_past_due_job(db_session):
    """
    Test that the worker picks up a job whose scheduled_at time has passed.
    """
    register("success")(success_job)
    queue = Queue(name="default_queue")
    db_session.add(queue)
    db_session.commit()

    # Schedule a job to run one hour ago
    past_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    job = Job(type="success", payload=[1, 1], queue_id=queue.id, scheduled_at=past_time)
    db_session.add(job)
    db_session.commit()

    # Run a processing cycle
    worker = Worker(queues=["default_queue"], enable_metrics=False)
    worker._process_job()

    # The job should have been processed
    db_session.expire_all()
    processed_job = db_session.get(Job, job.id)
    assert processed_job.status == JobStatus.done
    assert processed_job.result == 2
    assert processed_job.locked_by is not None
