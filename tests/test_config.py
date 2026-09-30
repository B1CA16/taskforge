from taskforge.config import settings
from taskforge.task_queue.models import Job, Queue


def test_job_uses_default_max_attempts(db_session):
    """
    Verify that a job gets the default max_attempts from settings when no value is provided.
    """
    # Ensure the setting has its default value
    assert settings.DEFAULT_MAX_ATTEMPTS == 3

    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    # Create a job without specifying max_attempts
    job = Job(type="test", queue_id=queue.id)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert job.max_attempts == settings.DEFAULT_MAX_ATTEMPTS


def test_job_overrides_default_max_attempts(db_session):
    """
    Verify that max_attempts can be set on a per-job basis, overriding the global default.
    """
    queue = Queue(name="default")
    db_session.add(queue)
    db_session.commit()

    # Create a job and explicitly set max_attempts
    job = Job(type="test", queue_id=queue.id, max_attempts=10)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert job.max_attempts == 10


def test_config_can_be_changed_by_env(monkeypatch):
    """
    Verify that the global setting can be changed via an environment variable.
    """
    # Use monkeypatch to set an environment variable for the duration of this test
    monkeypatch.setenv("DEFAULT_MAX_ATTEMPTS", "5")

    # We need to reload the settings module to make it pick up the new env var
    import importlib

    importlib.reload(settings)

    assert settings.DEFAULT_MAX_ATTEMPTS == 5

    # It's good practice to restore the original state after the test,
    # though pytest's monkeypatch handles this automatically.
    monkeypatch.undo()
    importlib.reload(settings)
    assert settings.DEFAULT_MAX_ATTEMPTS == 3
