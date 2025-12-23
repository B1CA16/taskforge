import pytest
from sqlalchemy import select
from taskforge.db.connection import engine, get_session
from taskforge.task_queue.models import Base, Job, Queue


def test_insert_job(db_session):
    # Create a queue
    queue = Queue(name="default_queue")
    db_session.add(queue)
    db_session.commit()
    db_session.refresh(queue)  # Refresh to get the generated ID

    # Create a job
    job = Job(type="test_job_type", queue_id=queue.id, status="pending")
    db_session.add(job)
    db_session.commit()

    stmt = select(Job).filter_by(type="test_job_type")
    saved_job = db_session.execute(stmt).scalars().first()
    print(f"Saved job: {saved_job.type}, status: {saved_job.status}")


if __name__ == "__main__":
    test_insert_job()
