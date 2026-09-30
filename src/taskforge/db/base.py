"""Engine and session factory, created lazily on first use.

Nothing here touches the database, the environment or ``.env`` at import time,
so ``import taskforge`` is always safe (docs builds, ``--help``, tests...).
"""

from __future__ import annotations

import os
import threading

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# Re-entrant: get_session_factory() holds it while calling get_engine().
_lock = threading.RLock()
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_database_url() -> str:
    """Return the configured database URL.

    Reads ``TASKFORGE_DATABASE_URL`` first, then ``DATABASE_URL``. If neither is
    set, a ``.env`` file in the working directory is loaded (without overriding
    existing variables) and the lookup is retried.

    Raises:
        RuntimeError: If no database URL is configured.
    """
    url = os.getenv("TASKFORGE_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        from dotenv import load_dotenv

        load_dotenv()
        url = os.getenv("TASKFORGE_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "No database configured. Set TASKFORGE_DATABASE_URL (or DATABASE_URL), "
            "e.g. postgresql+psycopg://user:password@localhost:5432/app"
        )
    return url


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    # SQLite ignores FOREIGN KEY constraints unless asked, per connection.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first call."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                engine = create_engine(get_database_url())
                if engine.dialect.name == "sqlite":
                    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
                _engine = engine
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory, creating it on first call."""
    global _session_factory
    if _session_factory is None:
        with _lock:
            if _session_factory is None:
                _session_factory = sessionmaker(
                    bind=get_engine(),
                    autoflush=False,
                    expire_on_commit=False,
                )
    return _session_factory


def reset_engine() -> None:
    """Dispose of the engine so the next call re-reads the configuration.

    Mainly useful in tests that switch databases.
    """
    global _engine, _session_factory
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _session_factory = None


def __getattr__(name: str):
    # Backwards compatibility: ``from taskforge.db.base import engine, SessionLocal``
    # still works, but now resolves lazily instead of at import time.
    if name == "engine":
        return get_engine()
    if name == "SessionLocal":
        return get_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
