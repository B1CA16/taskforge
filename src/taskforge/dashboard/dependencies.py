"""FastAPI dependencies."""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from taskforge.db.base import get_session_factory


def get_db() -> Iterator[Session]:
    """Yield a database session for one request, and close it afterwards."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
