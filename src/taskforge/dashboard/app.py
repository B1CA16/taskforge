"""The dashboard web app: HTML pages plus the JSON API under `/api`.

Run it with any ASGI server, e.g. `uvicorn taskforge.dashboard.app:app`. The
dashboard has no authentication yet, so keep it bound to `127.0.0.1` or behind a
proxy that handles auth.
"""

import contextlib
import datetime
import os

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taskforge import __version__
from taskforge.dashboard.api import router as api_router
from taskforge.dashboard.dependencies import get_db
from taskforge.task_queue.models import Job, JobStatus, Queue, WorkerRecord, WorkerStatus
from taskforge.utils.time import ensure_utc, utcnow

app = FastAPI(title="TaskForge Dashboard", version=__version__)
app.include_router(api_router)

_base_dir = os.path.dirname(os.path.abspath(__file__))
_templates_dir = os.path.join(_base_dir, "templates")
_static_dir = os.path.join(_base_dir, "static")

templates = Jinja2Templates(directory=_templates_dir)

if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# --- Jinja2 template filters ---


def format_duration(seconds: float | None) -> str:
    """Format a duration compactly: `850ms`, `12.3s` or `4m 5s`."""
    if seconds is None:
        return "N/A"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.0f}s"


def format_datetime(dt: datetime.datetime | None) -> str:
    """Format a timestamp as `YYYY-MM-DD HH:MM:SS` (UTC), or `N/A`."""
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def time_ago(dt: datetime.datetime | None) -> str:
    """Format how long ago a timestamp was, in the largest whole unit: `5m ago`."""
    if dt is None:
        return "N/A"
    now = utcnow()
    dt = ensure_utc(dt)
    diff = now - dt
    seconds = diff.total_seconds()
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


templates.env.filters["format_duration"] = format_duration
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["time_ago"] = time_ago


# --- Dashboard pages (server-rendered with HTMX) ---


@app.get("/", response_class=HTMLResponse)
def dashboard_overview(request: Request, db: Session = Depends(get_db)):
    """Overview page: job totals, per-queue counts, workers and the 10 latest failures."""
    stmt = (
        select(Queue.name, Job.status, func.count(Job.id))
        .join(Queue, Job.queue_id == Queue.id)
        .group_by(Queue.name, Job.status)
    )
    rows = db.execute(stmt).all()

    queue_map = {}
    for queue_name, status, count in rows:
        if queue_name not in queue_map:
            queue_map[queue_name] = {
                "name": queue_name,
                "pending": 0,
                "running": 0,
                "done": 0,
                "failed": 0,
                "dead": 0,
                "total": 0,
            }
        queue_map[queue_name][status.value] = count
        queue_map[queue_name]["total"] += count

    queues = list(queue_map.values())
    total_jobs = sum(q["total"] for q in queues)
    total_pending = sum(q["pending"] for q in queues)
    total_running = sum(q["running"] for q in queues)
    total_done = sum(q["done"] for q in queues)
    total_dead = sum(q["dead"] for q in queues)

    now = utcnow()
    workers_stmt = select(WorkerRecord).order_by(WorkerRecord.started_at.desc())
    workers_raw = db.execute(workers_stmt).scalars().all()
    workers = []
    for w in workers_raw:
        effective_status = w.status.value
        # A worker killed without shutting down still says "online"; its stale
        # heartbeat is the only sign that it's gone.
        if (
            w.status == WorkerStatus.online
            and w.last_heartbeat_at
            and (now - ensure_utc(w.last_heartbeat_at)).total_seconds() > 60
        ):
            effective_status = "lost"
        workers.append(
            {
                "id": w.id,
                "hostname": w.hostname,
                "pid": w.pid,
                "status": effective_status,
                "queues": w.queues or [],
                "started_at": w.started_at,
                "last_heartbeat_at": w.last_heartbeat_at,
            }
        )

    total_workers_online = sum(1 for w in workers if w["status"] == "online")

    failures_stmt = (
        select(Job, Queue.name)
        .join(Queue, Job.queue_id == Queue.id)
        .where(Job.status.in_([JobStatus.dead, JobStatus.failed]))
        .order_by(Job.updated_at.desc())
        .limit(10)
    )
    recent_failures = []
    for job, qname in db.execute(failures_stmt).all():
        recent_failures.append(
            {
                "id": job.id,
                "type": job.type,
                "status": job.status.value,
                "queue_name": qname,
                "error_message": (job.error_message or "")[:200],
                "updated_at": job.updated_at,
            }
        )

    return templates.TemplateResponse(
        request,
        "overview.html",
        {
            "total_jobs": total_jobs,
            "total_pending": total_pending,
            "total_running": total_running,
            "total_done": total_done,
            "total_dead": total_dead,
            "total_workers_online": total_workers_online,
            "queues": queues,
            "workers": workers,
            "recent_failures": recent_failures,
        },
    )


@app.get("/jobs", response_class=HTMLResponse)
def dashboard_jobs(
    request: Request,
    status: str | None = None,
    job_type: str | None = None,
    queue: str | None = None,
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
):
    """Jobs page: filterable by status, job type and queue, 25 jobs per page.

    HTMX requests (header `HX-Request: true`) get only the table, so filtering and
    paging update in place.
    """
    per_page = 25
    offset = (page - 1) * per_page

    stmt = (
        select(Job, Queue.name)
        .join(Queue, Job.queue_id == Queue.id)
        .order_by(Job.created_at.desc())
    )

    # An unknown status (e.g. from a stale bookmark) shows all jobs instead of an error.
    if status:
        with contextlib.suppress(ValueError):
            stmt = stmt.where(Job.status == JobStatus(status))

    if job_type:
        stmt = stmt.where(Job.type == job_type)

    if queue:
        stmt = stmt.where(Queue.name == queue)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = db.execute(count_stmt).scalar() or 0
    total_pages = max(1, (total_count + per_page - 1) // per_page)

    stmt = stmt.offset(offset).limit(per_page)

    jobs = []
    for job, qname in db.execute(stmt).all():
        duration = None
        if job.started_at and job.completed_at:
            duration = (job.completed_at - job.started_at).total_seconds()
        jobs.append(
            {
                "id": job.id,
                "type": job.type,
                "status": job.status.value,
                "queue_name": qname,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
                "tags": job.tags or {},
                "created_at": job.created_at,
                "duration": duration,
            }
        )

    job_types = [r[0] for r in db.execute(select(Job.type).distinct()).all()]
    queue_names = [r[0] for r in db.execute(select(Queue.name).distinct()).all()]

    is_htmx = request.headers.get("HX-Request") == "true"
    template = "partials/jobs_table.html" if is_htmx else "jobs.html"

    return templates.TemplateResponse(
        request,
        template,
        {
            "jobs": jobs,
            "page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "status_filter": status or "",
            "type_filter": job_type or "",
            "queue_filter": queue or "",
            "job_types": job_types,
            "queue_names": queue_names,
        },
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def dashboard_job_detail(request: Request, job_id: str, db: Session = Depends(get_db)):
    """Job detail page: payload, result, last error, timing, and a replay button for dead jobs."""
    stmt = select(Job, Queue.name).join(Queue, Job.queue_id == Queue.id).where(Job.id == job_id)
    row = db.execute(stmt).first()

    if not row:
        return HTMLResponse(content="<h1>Job not found</h1>", status_code=404)

    job, queue_name = row
    duration = None
    if job.started_at and job.completed_at:
        duration = (job.completed_at - job.started_at).total_seconds()

    return templates.TemplateResponse(
        request,
        "job_detail.html",
        {
            "job": job,
            "queue_name": queue_name,
            "duration": duration,
        },
    )
