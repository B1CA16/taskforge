import pytest
import logging
from taskforge.cli.main import view_dead_letter_queue
from taskforge.task_queue.models import Job, JobStatus, Queue

def test_view_dead_letter_queue(db_session, caplog):
    """
    Test that the CLI command for viewing the dead-letter queue
    correctly displays jobs with a 'dead' status.
    """
    # Arrange: Create a queue and a dead job
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    dead_job = Job(
        type="failed_task",
        status=JobStatus.dead,
        queue_id=queue.id,
        attempts=3,
        max_attempts=3,
        error_message="Final error message"
    )
    db_session.add(dead_job)
    db_session.commit()

    # Act: Run the function that the CLI calls
    with caplog.at_level(logging.INFO): # Ensure INFO level messages are captured
        view_dead_letter_queue()

    # Assert: Check that the log output contains the expected JSON structure
    assert any(
        record.event == "DeadLetterQueueStart"
        for record in caplog.records
    )
    assert any(
        record.__dict__.get('job_id') == str(dead_job.id) and
        record.__dict__.get('job_type') == "failed_task" and
        record.__dict__.get('attempts') == "3/3" and
        record.__dict__.get('error') == "Final error message" and
        record.__dict__.get('event') == "DeadJobDetails"
        for record in caplog.records
    )

def test_view_empty_dead_letter_queue(db_session, caplog):
    """
    Test that a friendly message is shown when the dead-letter queue is empty.
    """
    # Act: Run the function with no dead jobs in the db
    with caplog.at_level(logging.INFO): # Ensure INFO level messages are captured
        view_dead_letter_queue()

    # Assert
    assert any(
        record.event == "DeadLetterQueueEmpty"
        for record in caplog.records
    )
