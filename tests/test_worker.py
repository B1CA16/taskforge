import pytest
from taskforge.jobs.registry import register, get_job_func, _job_registry
from taskforge.worker.executor import execute_job
from taskforge.worker.worker import Worker
from taskforge.task_queue.models import Job, JobStatus, Queue


# Sample functions to be used as jobs
def success_job(x, y):
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
    result, error = execute_job(job)

    assert error is None
    assert result == 5


def test_execute_failing_job(db_session):
    register("failure")(failure_job)
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    job = Job(type="failure", queue_id=queue.id)
    result, error = execute_job(job)

    assert result is None
    assert "ValueError: This job intentionally fails" in error


# --- Worker Tests ---


def test_worker_claims_job(db_session):
    # Register a dummy job
    register("process_data")(success_job)

    # Create a queue and a pending job
    queue = Queue(name="default_queue")
    db_session.add(queue)
    db_session.commit()
    job = Job(
        type="process_data",
        payload={"x": 2, "y": 3},
        status=JobStatus.pending,
        queue_id=queue.id,
    )
    db_session.add(job)
    db_session.commit()

    # Instantiate a worker and run one processing cycle
    worker = Worker(queues=["default_queue"])
    worker._process_job()

    # Verify the job was processed
    processed_job = db_session.get(Job, job.id)
    db_session.refresh(processed_job)  # Refresh from DB
    assert processed_job.status == JobStatus.done
    assert processed_job.locked_by == worker.worker_id
    assert processed_job.result == 5


def test_worker_handles_failed_job(db_session):
    # Register the failing job
    register("failing_task")(failure_job)

    # Create a queue and a pending job with no retries left
    queue = Queue(name="default_queue")
    db_session.add(queue)
    db_session.commit()
    job = Job(
        type="failing_task",
        status=JobStatus.pending,
        queue_id=queue.id,
        max_attempts=1,
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()

    # Instantiate a worker and run one processing cycle
    worker = Worker(queues=["default_queue"])
    worker._process_job()

    # Verify the job failed and was moved to the dead-letter queue
    processed_job = db_session.get(Job, job.id)
    db_session.refresh(processed_job)  # Refresh from DB
    assert processed_job.status == JobStatus.dead
    assert processed_job.locked_by == worker.worker_id
    assert "ValueError: This job intentionally fails" in processed_job.error_message


def test_worker_retries_job(db_session):
    # Register the failing job
    register("failing_task")(failure_job)

    # Create a queue and a pending job with max_attempts
    queue = Queue(name="default_queue")
    db_session.add(queue)
    db_session.commit()
    job = Job(
        type="failing_task", status=JobStatus.pending, queue_id=queue.id, max_attempts=3
    )
    db_session.add(job)
    db_session.commit()

    # Run one processing cycle
    worker = Worker(queues=["default_queue"])
    worker._process_job()

    # Verify the job is scheduled for retry
    processed_job = db_session.get(Job, job.id)
    db_session.refresh(processed_job)
    assert processed_job.status == JobStatus.pending  # Should be pending for retry
    assert processed_job.attempts == 1
    assert processed_job.scheduled_at is not None
    assert (
        processed_job.scheduled_at - processed_job.updated_at
    ).total_seconds() > 19  # 10 * (2**1)


def test_worker_moves_job_to_dead_state(db_session):
    # Register the failing job
    register("failing_task")(failure_job)

    # Create a job that has one attempt left
    queue = Queue(name="default_queue")
    db_session.add(queue)
    db_session.commit()
    job = Job(
        type="failing_task",
        status=JobStatus.pending,
        queue_id=queue.id,
        attempts=2,
        max_attempts=3,
    )
    db_session.add(job)
    db_session.commit()

    # Run one processing cycle
    worker = Worker(queues=["default_queue"])
    worker._process_job()

    # Verify the job is moved to the dead state
    processed_job = db_session.get(Job, job.id)
    db_session.refresh(processed_job)
    assert processed_job.status == JobStatus.dead
    assert processed_job.attempts == 3
