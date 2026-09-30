from taskforge.db.base import get_session_factory


def get_db():
    """FastAPI dependency that provides a database session per request."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
