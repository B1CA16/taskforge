"""Shared fixtures.

The suite drops and recreates every table, so it only runs against a database
whose name contains "test". By default that's the disposable Postgres from
``docker compose up -d test-db``; override with TASKFORGE_TEST_DATABASE_URL.
"""

import os

import pytest
from sqlalchemy.engine import make_url

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5436/taskforge_test"


def _check_is_test_database(url: str) -> None:
    parsed = make_url(url)
    database = parsed.database or ""
    in_memory_sqlite = parsed.get_backend_name() == "sqlite" and database in ("", ":memory:")
    if not in_memory_sqlite and "test" not in os.path.basename(database).lower():
        raise pytest.UsageError(
            f"Refusing to run the test suite against {parsed.render_as_string(hide_password=True)}: "
            "the tests DROP ALL TABLES, so the database name must contain 'test'."
        )


TEST_DATABASE_URL = os.getenv("TASKFORGE_TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
_check_is_test_database(TEST_DATABASE_URL)

# Point TaskForge at the test database before anything creates the engine, and
# make sure a developer's .env / DATABASE_URL can never be picked up instead.
os.environ["TASKFORGE_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from taskforge.db.base import get_engine  # noqa: E402
from taskforge.db.connection import get_session  # noqa: E402
from taskforge.task_queue.models import Base  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    engine = get_engine()
    try:
        with engine.connect():
            pass
    except Exception as exc:
        pytest.exit(
            f"Cannot connect to the test database ({exc.__class__.__name__}). "
            "Start it with: docker compose up -d test-db",
            returncode=2,
        )
    return engine


@pytest.fixture(scope="function")
def db_session(engine):
    """Provide a clean database (all tables recreated) and a session on it."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with get_session() as session:
        yield session
    Base.metadata.drop_all(bind=engine)
