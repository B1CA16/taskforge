# TaskForge

**Background jobs for Python, stored in your Postgres database. No Redis, no broker.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Status: alpha (0.2.0.dev).** The API will change before 1.0. Pre-releases are on PyPI as
> [`taskforge-queue`](https://pypi.org/project/taskforge-queue/) (`pip install --pre taskforge-queue`); the first stable release is 0.2.0.
> See [`docs/revamp/`](https://github.com/B1CA16/taskforge/blob/main/docs/revamp/) for the audit, spec and roadmap.

Some work is too slow to do inside a web request: sending an email, resizing an image, generating a report. TaskForge moves it to a background **worker**. Jobs are rows in a **queue** table in your Postgres database, so they survive restarts, and a worker claims each one with `SELECT … FOR UPDATE SKIP LOCKED`, which means you can run as many workers as you like.

## Features

- **Postgres-backed queue.** Jobs are durable and safe to consume from many workers at once.
- **`@register` decorator.** Any function can be a job.
- **Retries with exponential backoff**, then a **dead-letter** state for jobs that keep failing, with one-click replay.
- **Scheduled jobs.** Run no earlier than a given time.
- **Tags.** Attach key/value metadata to jobs and filter by it.
- **Worker registry with heartbeats.** See which workers are online, offline or lost.
- **Web dashboard** (FastAPI + HTMX): overview, job search, job details, replay.
- **Prometheus metrics** exported by each worker.
- **CLI** for stats, history, workers, dead-letter and replay.
- **Graceful shutdown.** On Ctrl+C, SIGTERM or Ctrl+Break, the worker finishes the current job first.

Not implemented yet: reclaiming jobs from crashed workers, concurrency within a worker, priorities, cron schedules, dashboard authentication. See the [roadmap](https://github.com/B1CA16/taskforge/blob/main/docs/revamp/03-PRIORITIES.md).

## Requirements

- Python 3.10+
- PostgreSQL 13+. SQLite works for the dashboard and CLI but **not** for workers, which need `SKIP LOCKED`.

## Installation

```powershell
pip install --pre taskforge-queue
```

Or from source, for development:

```powershell
git clone https://github.com/B1CA16/taskforge.git
cd taskforge
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

<details><summary>macOS / Linux</summary>

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```
</details>

## Quick start

**1. Point TaskForge at a database.** Copy `.env.example` to `.env` and set the URL, or set it for the current PowerShell session:

```powershell
$env:TASKFORGE_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5435/postgres"
```

No Postgres yet? See [docs/DOCKER_PG_SETUP.md](https://github.com/B1CA16/taskforge/blob/main/docs/DOCKER_PG_SETUP.md).

**2. Create the tables** (safe to re-run; it never drops anything):

```powershell
python -m taskforge.cli.main init-db
```

**3. Define jobs.** From [`demo_client/my_sample_jobs.py`](https://github.com/B1CA16/taskforge/blob/main/demo_client/my_sample_jobs.py):

```python
from taskforge.jobs.registry import register

@register("add_numbers")
def add_numbers(a: int, b: int, logger=None):
    if logger:
        logger.info(f"Adding {a} and {b}")
    return a + b
```

**4. Start a worker**, in terminal 1:

```powershell
python demo_client\run_worker.py
```

**5. Enqueue jobs**, in terminal 2:

```powershell
python demo_client\enqueue_job.py
```

The worker picks the jobs up immediately. One of the demo jobs fails on purpose, so you'll also see a retry being scheduled and a job moving to the dead-letter queue.

## Usage

### Defining jobs

- Decorate a function with `@register("job_type")`. Each name must be unique; registering a different function under an existing name raises `ValueError`.
- A `dict` payload is passed as keyword arguments, and a `list` payload as positional arguments.
- If the function has a `logger` parameter, TaskForge injects a logger that adds `job_id`, `job_type` and `worker_id` to every record.
- The return value is stored as the job's `result` and must be JSON-serializable.
- Jobs can run more than once (at-least-once delivery), so make them **idempotent**.

### Enqueuing jobs

```python
from datetime import datetime, timedelta, timezone
from taskforge.task_queue.db import enqueue_single_job

enqueue_single_job(
    "add_numbers",                     # job_type used in @register
    {"a": 1, "b": 2},                  # dict -> kwargs, list -> args
    queue_name="default_queue",
    max_attempts=5,                    # overrides DEFAULT_MAX_ATTEMPTS
    scheduled_at=datetime.now(timezone.utc) + timedelta(minutes=5),  # naive = UTC
    tags={"team": "billing"},
)
```

### Running workers

```python
from taskforge.config.logging import setup_logging
from taskforge.worker.worker import Worker
import my_jobs  # importing the module registers the jobs

setup_logging()  # TaskForge never configures logging on its own
Worker(queues=["default_queue"]).run()
```

`Worker` options: `queues`, `poll_interval` (seconds to wait when idle, default 1), `enable_metrics`, `metrics_port` (default `TASKFORGE_METRICS_PORT` or 9464), `handle_signals`.

A failed job is retried after `10 × 2^attempt` seconds (20 s, 40 s, …) and moves to `dead` after `max_attempts`.

### Job states

| Status | Meaning |
|---|---|
| `pending` | Waiting for its first run |
| `running` | Claimed by a worker |
| `failed` | Last attempt failed; retry scheduled at `scheduled_at` |
| `done` | Finished successfully |
| `dead` | Out of attempts; inspect it, then replay it |

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `TASKFORGE_DATABASE_URL` (or `DATABASE_URL`) | none (required) | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pw@host:5432/db`. A `.env` file in the working directory is read if neither is set. |
| `DEFAULT_MAX_ATTEMPTS` | `3` | Attempts per job (including the first run) |
| `TASKFORGE_METRICS_PORT` | `9464` | Port for each worker's Prometheus exporter |

## CLI

```powershell
python -m taskforge.cli.main init-db                   # create missing tables
python -m taskforge.cli.main stats                     # job counts per queue and status
python -m taskforge.cli.main history --status dead --tag team=billing --limit 50
python -m taskforge.cli.main workers                   # registered workers and heartbeat status
python -m taskforge.cli.main dead-letter               # dead jobs with their last error
python -m taskforge.cli.main replay <job_id>           # re-enqueue a dead job (once; --force to repeat)
```

## Dashboard

```powershell
python demo_client\run_dashboard.py
```

Open http://127.0.0.1:8000. The JSON API is at `/api/*` and the interactive docs at `/docs`.

> ⚠️ The dashboard has **no authentication yet**. Keep it on `127.0.0.1` or behind a proxy that handles auth.

## Metrics

Each worker serves Prometheus metrics at `http://<host>:9464/metrics`:
- `taskforge_jobs_processed_total{queue,job_type,status}`
- `taskforge_jobs_enqueued_total{queue,job_type}` (counted in the process that enqueues)
- `taskforge_job_execution_duration_seconds`
- `taskforge_queue_depth{queue,status}`
- `taskforge_active_workers{queue}`

If the port is already taken (for example, by a second worker on the same machine), the worker logs a warning and keeps running without an exporter.

## Development

The test suite runs against a disposable Postgres in Docker (port 5436, data in memory):

```powershell
docker compose up -d test-db
pytest
```

The suite **drops all tables**, so it refuses to run unless the database name contains `test`. Point it elsewhere with `TASKFORGE_TEST_DATABASE_URL`. See [TESTING_STRATEGY.md](https://github.com/B1CA16/taskforge/blob/main/TESTING_STRATEGY.md).

## License

MIT. See [LICENSE](https://github.com/B1CA16/taskforge/blob/main/LICENSE).
