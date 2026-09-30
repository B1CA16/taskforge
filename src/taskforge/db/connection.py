"""Session context manager used throughout TaskForge."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from taskforge.db.base import get_engine, get_session_factory


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a new SQLAlchemy session and close it afterwards.

    Usage:
        with get_session() as session:
            ...
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def __getattr__(name: str):
    # Backwards compatibility for `from taskforge.db.connection import engine`.
    if name == "engine":
        return get_engine()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
