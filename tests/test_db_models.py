import pytest
from sqlalchemy.exc import IntegrityError
from taskforge.task_queue.models import Job, Queue


def test_insert_job_and_queue(db_session):
    """
    Test basic insertion of a Queue and a Job, and verify the relationship.
    """
    # Create and save a queue
    queue = Queue(name="default_queue")
    db_session.add(queue)
    db_session.commit()
    db_session.refresh(queue)

    # Create and save a job associated with the queue
    job = Job(type="test_job", queue_id=queue.id)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    # Assertions
    assert job.id is not None
    assert job.queue_id == queue.id
    assert job.queue.name == "default_queue"
    assert len(queue.jobs) == 1
    assert queue.jobs[0].type == "test_job"


def test_queue_name_uniqueness(db_session):
    """
    Test that queue names must be unique.
    """
    # Create the first queue
    queue1 = Queue(name="unique_queue")
    db_session.add(queue1)
    db_session.commit()

    # Attempt to create a second queue with the same name
    queue2 = Queue(name="unique_queue")
    db_session.add(queue2)

    # Expect an IntegrityError on commit
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_job_requires_valid_queue(db_session):
    """
    Test that a job cannot be created with a non-existent queue_id.
    """
    # Attempt to create a job with a queue_id that doesn't exist
    job = Job(type="test_job", queue_id="non_existent_queue_id")
    db_session.add(job)

    # Expect an IntegrityError due to the foreign key constraint
    with pytest.raises(IntegrityError):
        db_session.commit()