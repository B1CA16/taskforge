"""Response models for the dashboard's JSON API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class QueueStats(BaseModel):
    """Job counts for one queue, by status."""

    name: str
    pending: int = 0
    running: int = 0
    done: int = 0
    failed: int = 0
    dead: int = 0
    total: int = 0


class JobSummary(BaseModel):
    """A job as shown in lists: identity, status and timing, without payload or result."""

    id: str
    type: str
    status: str
    queue_name: str
    attempts: int
    max_attempts: int
    tags: dict | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None

    model_config = {"from_attributes": True}


class JobDetail(JobSummary):
    """Everything about one job, including its payload, result and last error."""

    payload: dict | list | None = None
    result: Any = None  # any JSON value the handler returned, not only dicts and lists
    error_message: str | None = None
    locked_by: str | None = None
    locked_at: datetime | None = None
    scheduled_at: datetime | None = None
    updated_at: datetime | None = None


class WorkerSummary(BaseModel):
    """A registered worker.

    `status` is `lost` when the worker says it's online but hasn't sent a heartbeat
    for over 60 seconds.
    """

    id: str
    hostname: str
    pid: int
    status: str
    queues: list[str]
    started_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    stopped_at: datetime | None = None
    uptime_seconds: float | None = None

    model_config = {"from_attributes": True}


class OverviewStats(BaseModel):
    """Totals for the dashboard's overview page."""

    total_jobs: int
    total_pending: int
    total_running: int
    total_done: int
    total_dead: int
    total_workers_online: int
    queues: list[QueueStats]
    recent_failures: list[JobSummary]
