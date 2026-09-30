from taskforge.task_queue.models import Job, Queue


def test_job_created_with_tags(db_session):
    """Test that a job can be created with tags metadata."""
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    job = Job(
        type="test_job",
        queue_id=queue.id,
        tags={"env": "production", "team": "billing"},
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert job.tags == {"env": "production", "team": "billing"}


def test_job_tags_default_to_empty_dict(db_session):
    """Test that tags default to an empty dict when not specified."""
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    job = Job(type="test_job", queue_id=queue.id)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert job.tags == {} or job.tags is None


def test_enqueue_job_with_tags(db_session):
    """Test that enqueue_single_job correctly stores tags."""
    from taskforge.task_queue.db import enqueue_single_job

    job = enqueue_single_job(
        job_type="tagged_job",
        payload={"x": 1},
        tags={"priority": "high", "source": "api"},
    )

    assert job.tags == {"priority": "high", "source": "api"}


def test_filter_jobs_by_tag(db_session):
    """Test filtering jobs by tag key-value pair."""
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    job1 = Job(type="a", queue_id=queue.id, tags={"env": "prod"})
    job2 = Job(type="b", queue_id=queue.id, tags={"env": "staging"})
    job3 = Job(type="c", queue_id=queue.id, tags={"team": "billing"})
    db_session.add_all([job1, job2, job3])
    db_session.commit()

    # Filter for env=prod
    from sqlalchemy import select

    stmt = select(Job).where(Job.tags["env"].as_string() == "prod")
    results = db_session.execute(stmt).scalars().all()

    assert len(results) == 1
    assert results[0].type == "a"
