from taskforge.db.base import engine, SessionLocal
from taskforge.task_queue.models import Base


def get_session():
    """
    Returns a new SQLAlchemy session.
    Usage:
        with get_session() as session:
            ...
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
