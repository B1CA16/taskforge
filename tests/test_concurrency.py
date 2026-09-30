import threading
import time
from collections import Counter

import pytest

from taskforge.jobs.registry import _job_registry, register
from taskforge.task_queue.models import Job, JobStatus, Queue
from taskforge.worker.worker import Worker

# A shared, thread-safe list to record which jobs get processed
processed_jobs = Counter()


# A simple job that appends its ID to the shared list
@register("concurrent_job")
def concurrent_job(job_id):
    global processed_jobs
    processed_jobs[job_id] += 1
    time.sleep(0.1)  # Simulate some work


@pytest.fixture(autouse=True)
def clear_registry_and_counter():
    """Clears the registry and counter before and after each test."""
    _job_registry.clear()
    processed_jobs.clear()
    # Re-register the concurrent_job for each test
    register("concurrent_job")(concurrent_job)
    yield
    _job_registry.clear()
    processed_jobs.clear()


def test_concurrent_workers_process_jobs_once(db_session):
    """
    Test that multiple workers running concurrently process each job exactly once.
    """
    # Arrange: Create a queue and multiple jobs
    queue_name = "concurrent_queue"
    queue = Queue(name=queue_name)
    db_session.add(queue)
    db_session.commit()

    job_ids = []
    for i in range(10):
        job = Job(
            type="concurrent_job",
            payload={"job_id": i},
            queue_id=queue.id,
            status=JobStatus.pending,
        )
        db_session.add(job)
        job_ids.append(i)
    db_session.commit()

    # Act: Start multiple workers in separate threads
    num_workers = 3
    workers = [Worker(queues=[queue_name], enable_metrics=False) for _ in range(num_workers)]
    threads = [threading.Thread(target=worker.run) for worker in workers]

    for t in threads:
        t.start()

    # Let the workers run for a short period
    # This needs to be long enough for all jobs to be processed
    time.sleep(5)

    # Stop the workers
    for worker in workers:
        worker.stop()
    for t in threads:
        t.join()

    # Assert: Check that each job was processed exactly once
    assert len(processed_jobs) == len(job_ids)
    for job_id in job_ids:
        assert processed_jobs[job_id] == 1, (
            f"Job {job_id} was processed {processed_jobs[job_id]} times!"
        )

    # Additionally, verify that all jobs in the DB are 'done'
    db_session.expire_all()
    jobs_in_db = db_session.query(Job).filter(Job.queue_id == queue.id).all()
    assert all(job.status == JobStatus.done for job in jobs_in_db)
