from sqlalchemy import Column, String, Integer, Text, JSON, Enum, DateTime
from sqlalchemy.ext.declarative import declarative_base
import enum
import datetime
import uuid

Base = declarative_base()


class JobStatus(enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    dead = "dead"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String, nullable=False)
    payload = Column(JSON, nullable=True)
    status = Column(Enum(JobStatus), default=JobStatus.pending, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )
    scheduled_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    locked_by = Column(String, nullable=True)
    locked_at = Column(DateTime, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
