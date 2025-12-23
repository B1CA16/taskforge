from sqlalchemy import Column, String, Integer, Text, JSON, Enum, DateTime, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from taskforge.config.settings import DEFAULT_MAX_ATTEMPTS
import enum
import datetime
import uuid

Base = declarative_base()


class Queue(Base):
    __tablename__ = "queues"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)

    jobs = relationship("Job", back_populates="queue")


class JobStatus(enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    dead = "dead"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    queue_id = Column(String, ForeignKey("queues.id"), nullable=False)
    type = Column(String, nullable=False)
    payload = Column(JSON, nullable=True)
    status = Column(Enum(JobStatus), default=JobStatus.pending, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )
    scheduled_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=DEFAULT_MAX_ATTEMPTS)
    locked_by = Column(String, nullable=True)
    locked_at = Column(DateTime, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    queue = relationship("Queue", back_populates="jobs")
