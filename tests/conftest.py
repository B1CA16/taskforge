import pytest
from taskforge.db.connection import engine, get_session
from taskforge.task_queue.models import Base


@pytest.fixture(scope="function")
def db_session():
    """
    Pytest fixture to provide a clean database session for each test function.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with get_session() as session:
        yield session
    Base.metadata.drop_all(bind=engine)
