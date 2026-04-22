from taskforge.db.base import SessionLocal


def get_db():
    """FastAPI dependency that provides a database session per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
