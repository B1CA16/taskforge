from typing import Any

from pydantic import BaseModel
from datetime import datetime


class QueueStats(BaseModel):
    name: str
    pending: int = 0
    running: int = 0
    done: int = 0
    failed: int = 0
    dead: int = 0
    total: int = 0


class JobSummary(BaseModel):
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
    payload: dict | list | None = None
    result: Any = None  # whatever the job returned: any JSON value
    error_message: str | None = None
    locked_by: str | None = None
    locked_at: datetime | None = None
    scheduled_at: datetime | None = None
    updated_at: datetime | None = None


class WorkerSummary(BaseModel):
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
    total_jobs: int
    total_pending: int
    total_running: int
    total_done: int
    total_dead: int
    total_workers_online: int
    queues: list[QueueStats]
    recent_failures: list[JobSummary]
