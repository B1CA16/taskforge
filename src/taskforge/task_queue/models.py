import enum
import uuid

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    text,
)
from sqlalchemy.orm import declarative_base, relationship

from taskforge.config import settings
from taskforge.utils.time import ensure_utc, utcnow

Base = declarative_base()


class UTCDateTime(TypeDecorator):
    """A timestamp that is always stored and returned as aware UTC.

    On Postgres this is ``timestamptz``, so comparisons with ``NOW()`` are
    correct whatever the server's timezone. On SQLite (no timezone support) the
    value is stored as naive UTC and re-tagged as UTC when loaded.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        value = ensure_utc(value)
        if value is not None and dialect.name == "sqlite":
            value = value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        return ensure_utc(value)


def _default_max_attempts() -> int:
    # Read at insert time (not import time) so env/config changes are honoured.
    return settings.DEFAULT_MAX_ATTEMPTS


class Queue(Base):
    __tablename__ = "queues"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)

    jobs = relationship("Job", back_populates="queue")


class JobStatus(enum.Enum):
    pending = "pending"  # waiting for its first run
    running = "running"  # claimed by a worker
    done = "done"  # finished successfully
    failed = "failed"  # last attempt failed; waiting for a retry at `scheduled_at`
    dead = "dead"  # out of attempts (or cancelled); needs manual action


class WorkerStatus(enum.Enum):
    online = "online"
    offline = "offline"
    lost = "lost"


class WorkerRecord(Base):
    __tablename__ = "workers"

    id = Column(String, primary_key=True)
    hostname = Column(String, nullable=False)
    pid = Column(Integer, nullable=False)
    status = Column(Enum(WorkerStatus), default=WorkerStatus.online, nullable=False)
    queues = Column(JSON, nullable=False, default=list)
    started_at = Column(UTCDateTime, default=utcnow)
    last_heartbeat_at = Column(UTCDateTime, default=utcnow)
    stopped_at = Column(UTCDateTime, nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    queue_id = Column(String, ForeignKey("queues.id"), nullable=False)
    type = Column(String, nullable=False)
    payload = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True, default=dict)
    status = Column(Enum(JobStatus), default=JobStatus.pending, nullable=False)
    created_at = Column(UTCDateTime, default=utcnow)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)
    scheduled_at = Column(UTCDateTime, nullable=True)
    started_at = Column(UTCDateTime, nullable=True)
    completed_at = Column(UTCDateTime, nullable=True)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=_default_max_attempts)
    locked_by = Column(String, nullable=True)
    locked_at = Column(UTCDateTime, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    queue = relationship("Queue", back_populates="jobs")

    __table_args__ = (
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_type", "type"),
        Index("ix_jobs_created_at", "created_at"),
        # Serves the worker's claim query: only claimable rows, in FIFO order.
        Index(
            "ix_jobs_claimable",
            "queue_id",
            "created_at",
            postgresql_where=text("status IN ('pending', 'failed')"),
            sqlite_where=text("status IN ('pending', 'failed')"),
        ),
    )
