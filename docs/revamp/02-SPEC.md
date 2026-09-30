# TaskForge — Product & Technical Spec

_Status: Draft v1 · 2026-09-25 · Owner: Francisco Ferreira_
_Baseline: `origin/main` @ `f3f0ad0`. See the audit for what already exists._
_Companion docs: [01-AUDIT.md](01-AUDIT.md) (current state) · [03-PRIORITIES.md](03-PRIORITIES.md) (ordered plan)_

---

## 1. Vision & positioning

> **TaskForge: background jobs for Python that live in your Postgres. No Redis, no broker, no surprises.**

### 1.1 Who it's for
Teams running a Python web app (FastAPI, Django, Flask, or plain scripts) who **already have Postgres** and want reliable background jobs without running and monitoring another piece of infrastructure.

### 1.2 Why someone would pick it over the alternatives

| | Celery / Dramatiq / RQ / arq | Procrastinate / PgQueuer | **TaskForge (target)** |
|---|---|---|---|
| Extra infra | Redis / RabbitMQ | None | **None** |
| Transactional enqueue | ✗ | ✓ | **✓ (first-class, SQLAlchemy session)** |
| Built-in dashboard | Flower (separate) | ✗ / minimal | **✓ bundled, mountable, auth'd** |
| Prometheus + Grafana out of the box | Plugins | ✗ | **✓ + shipped Grafana dashboard** |
| Sync *and* async jobs | Varies | Async-first | **✓ both** |
| Mental model | Large | Medium | **Small: one table, one decorator, one CLI** |

Differentiators to lean on:
1. **Transactional enqueue with your own SQLAlchemy session**: "the job exists if and only if your order row exists."
2. **Batteries-included operations**: dashboard, CLI, metrics and a Grafana board in one `pip install`.
3. **Boring and explainable**: every state transition is one SQL statement you can read in the docs.

### 1.3 Non-goals (explicit)
- Exactly-once execution. We guarantee at-least-once and document idempotency.
- Non-Postgres production backends (MySQL, Redis). SQLite is supported **for development and tests only**.
- Sub-millisecond latency or >50k jobs/s. Target: ~1–5k jobs/s on a modest Postgres (to be benchmarked).
- A general workflow engine like Airflow or Temporal. Simple chains/groups are in scope; DAG scheduling is not.

---

## 2. Decisions required before starting

| ID | Decision | Recommendation |
|---|---|---|
| D1 | **PyPI distribution name.** `taskforge` is taken. | Publish as **`taskforge-queue`** and keep `import taskforge`. The brand stays intact and only the pip command changes. Reserve the name on TestPyPI/PyPI now, with an empty `0.0.1` placeholder. |
| D2 | **Version reset.** | Go back to **`0.2.0`** and `Development Status :: 3 - Alpha`. Reserve `1.0.0` for a frozen public API plus a few external users. |
| D3 | **Breaking changes allowed?** | Yes. Nobody depends on it yet. Keep thin deprecated shims (`register`, `enqueue_single_job`) for one minor release to be kind to early readers of the README. |
| D4 | **Docs hosting.** | **MkDocs Material on GitHub Pages** (`b1ca16.github.io/taskforge`), versioned with `mike`. A custom domain can come later. |
| D5 | **Dashboard frontend stack.** | Keep what's on `main`: **FastAPI + Jinja2 + HTMX**, server-rendered. **Vendor** htmx (it's on unpkg today) and add Alpine.js / uPlot only where they're needed. No Node build step: it stays a pure-Python package and contributors don't need npm. |
| D6 | **License.** | Keep MIT. |

---

## 3. Public API (target for 0.2 → 0.4)

### 3.1 The app object: no import-time side effects
```python
# myproject/tasks.py
from taskforge import TaskForge

tf = TaskForge(
    database_url="postgresql+psycopg://app:pw@db/app",   # or engine=my_engine
    default_queue="default",
    default_max_attempts=3,
)

@tf.job(queue="emails", max_attempts=5, timeout=30, retry=tf.retry.exponential(base=2, max=600, jitter=True))
def send_welcome_email(user_id: int) -> None:
    ...

@tf.job()                        # async jobs are supported the same way
async def resize_image(path: str) -> str:
    ...
```
Rules:
- `import taskforge` never touches the DB, env vars or logging configuration.
- Settings come from constructor args, then `TASKFORGE_*` env vars (`TASKFORGE_DATABASE_URL`, fallback `DATABASE_URL`), then defaults. Implemented with a small dataclass (or `pydantic-settings` as an optional extra).
- Multiple `TaskForge` instances can coexist, which is what isolated tests need.

### 3.2 Enqueueing
```python
send_welcome_email.enqueue(user_id=42)                           # fire and forget
send_welcome_email.enqueue(user_id=42, _delay=timedelta(minutes=5))
send_welcome_email.enqueue(user_id=42, _run_at=dt, _priority=10, _queue="bulk")
send_welcome_email.enqueue(user_id=42, _unique_key="welcome:42")  # dedupe while pending/running

# Transactional: uses the caller's session and doesn't commit
with Session(engine) as s, s.begin():
    s.add(order)
    send_receipt.enqueue(order_id=order.id, _session=s)

# By name, for producers that don't import the job code
tf.enqueue("send_welcome_email", kwargs={"user_id": 42})

# Bulk: one INSERT … VALUES (…),(…)
tf.enqueue_many([send_welcome_email.build(user_id=i) for i in ids])
```
`enqueue()` returns a `JobHandle` (`id`, `status()`, `refresh()`, `result(timeout=...)`, `cancel()`).

### 3.3 Controlling retries from inside a job
```python
from taskforge import Retry, Abort

@tf.job()
def call_api(url):
    r = httpx.get(url)
    if r.status_code == 429:
        raise Retry(after=int(r.headers["Retry-After"]))  # custom delay, still counts as an attempt
    if r.status_code == 404:
        raise Abort("gone")                               # no retries, straight to dead
```
The job can also receive a `ctx: JobContext` parameter (`job_id`, `attempt`, `logger`, `is_cancelled()`, `heartbeat()`). This replaces the magic `logger` kwarg injection, which stays supported for compatibility.

### 3.4 Periodic jobs
```python
@tf.periodic(cron="*/15 * * * *", queue="maintenance")   # croniter
def cleanup_sessions(): ...
```
Exactly one enqueue per tick across all workers, guaranteed by a unique `(schedule_name, tick_at)` constraint.

### 3.5 Framework integrations (thin, optional extras)
- `taskforge.contrib.fastapi`: `mount_dashboard(app, tf, path="/taskforge", auth=...)`, plus a lifespan helper.
- `taskforge.contrib.django`: settings-based `TaskForge`, management commands (`manage.py taskforge worker`), admin link.
- `taskforge.contrib.flask`: extension with `init_app`.

---

## 4. Data model v2

It evolves the existing `jobs` / `queues` / `workers` tables through the **first Alembic migration**, which renames them, converts types and backfills. All timestamps are `timestamptz`. All IDs are native `uuid` on Postgres. The schema is managed by **Alembic migrations shipped inside the package** (`taskforge db upgrade`).

### `taskforge_jobs` (tables are prefixed so they don't collide with host app tables)
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `queue` | text NOT NULL | Denormalised name. Drops the join and the get-or-create race (B13). |
| `task_name` | text NOT NULL | |
| `args` / `kwargs` | jsonb | Replaces the ambiguous dict-or-list `payload`. |
| `status` | enum | `scheduled`, `pending`, `running`, `succeeded`, `failed` (awaiting retry), `dead`, `cancelled` |
| `priority` | smallint default 0 | Higher runs first. |
| `run_at` | timestamptz NOT NULL default now() | Replaces the nullable `scheduled_at`. |
| `attempts`, `max_attempts` | int | |
| `timeout_s` | int NULL | |
| `unique_key` | text NULL | Partial unique index `WHERE status IN ('scheduled','pending','running')`. |
| `worker_id` | uuid NULL | FK → `taskforge_workers` |
| `started_at`, `finished_at`, `heartbeat_at` | timestamptz | Used for latency metrics and the stale-job reaper. |
| `cancel_requested` | bool default false | Cooperative cancel of running jobs. This is missing today: `main` can't cancel at all. |
| `result` | jsonb NULL | Must be JSON-serialisable. If it isn't, the job fails with a clear error instead of getting stuck (fixes B1). |
| `last_error` | jsonb NULL | `{type, message, traceback}` |
| `parent_id` | uuid NULL | For chains/groups (phase 5). |
| `created_at`, `updated_at` | timestamptz | |

**Claim index**: `CREATE INDEX … ON taskforge_jobs (queue, priority DESC, run_at) WHERE status = 'pending';`

### `taskforge_job_events` (append-only, optional, pruned)
`(job_id, at, event, attempt, worker_id, detail jsonb)`. It drives the attempt timeline in the dashboard and the throughput charts, so the dashboard doesn't need Prometheus.

### `taskforge_workers`
`id, hostname, pid, queues text[], concurrency, version, started_at, heartbeat_at, status (running|draining|stopped)`. This replaces inferring "workers" from `locked_by`, which can't show idle workers.

### `taskforge_queues`
`name PK, paused bool, concurrency_limit int NULL, rate_limit jsonb NULL`. It's configuration only: a queue exists implicitly as soon as a job uses it.

### `taskforge_schedules`
`name PK, cron, task_name, kwargs, queue, enabled, last_tick_at`.

### Retention
`taskforge jobs prune --succeeded-older-than 7d --dead-older-than 30d`, which can also run as a built-in periodic job (configurable).

---

## 5. Worker v2

| Concern | Spec |
|---|---|
| **Concurrency** | `--concurrency N` thread pool for sync jobs, an event loop for `async def` jobs, and optional `--processes P` for CPU-bound work (a supervisor forks P children). |
| **Fetching** | Claim up to `free_slots` jobs per query (`LIMIT n`). Order by `priority DESC, run_at`. Filter by `queue = ANY(:queues)` and exclude paused queues. |
| **Wake-up** | Postgres `LISTEN taskforge_jobs`, with `NOTIFY` fired on enqueue. Falls back to polling (`poll_interval`, default 1 s) only when idle. This removes the 1 job/s cap (B4). |
| **Heartbeats** | The worker updates `taskforge_workers.heartbeat_at` and `heartbeat_at` on its running jobs every `heartbeat_interval` (default 10 s). |
| **Stale-job reaper** | Every worker runs it (it's idempotent): jobs `running` with `heartbeat_at < now() - stale_after` (default 60 s) go back to `pending`/`dead` per attempts, with an event logged. It builds on the `WorkerRecord` heartbeats that already exist. Fixes B1. |
| **Timeouts** | Sync jobs: soft timeout (the `JobContext` is flagged, logged) plus a hard timeout that marks the job failed and abandons the thread. In process mode it kills the child. Async jobs: `asyncio.timeout`. The limitations are documented honestly. |
| **Retries** | Pluggable `RetryPolicy`: `exponential(base, max, jitter)` (default), `linear`, `fixed`, or custom callables. `Retry(after=)` and `Abort` exceptions. `retry_on=(TransientError,)` filter. |
| **Cancellation** | Pending/scheduled jobs are cancelled immediately. Running jobs get `cancel_requested=true`, which the job can poll via `ctx.is_cancelled()`. The worker never overwrites a `cancelled` status (conditional `UPDATE … WHERE status='running'`). |
| **Shutdown** | SIGTERM/SIGINT: stop fetching, drain running jobs for up to `--shutdown-timeout` (default 30 s), then release unfinished jobs back to `pending`. A second signal means immediate exit. Works on Windows (CTRL_C / CTRL_BREAK). |
| **Hooks** | `on_job_start`, `on_job_success`, `on_job_failure`, `on_worker_start/stop`, used internally by metrics and tracing. Users can add their own (Sentry, etc.). |
| **Middleware** | Optional wrapper chain around job execution (DB session per job, tenant context, tracing span). |

All state transitions are single conditional `UPDATE … WHERE id=:id AND status=:expected RETURNING`, which prevents lost updates.

---

## 6. CLI

Built on **Typer** (or Click) + **Rich** for real tables. It's installed as the console script `taskforge`. Every command accepts `--app module:tf` (or `TASKFORGE_APP`) and `--json` for machine output.

```
taskforge worker     --app myproj.tasks:tf -q emails,default -c 8 [--processes 2]
taskforge dashboard  --app … --host 127.0.0.1 --port 8000
taskforge db         upgrade | downgrade | current | sql   # Alembic wrapper
taskforge queues     list | pause NAME | resume NAME
taskforge jobs       list [--status --queue --task --since] | show ID | retry ID… | cancel ID… | delete ID… | prune …
taskforge dead       list | retry --all [--task …]
taskforge workers    list
taskforge schedules  list | enable | disable | run-now NAME
taskforge stats      [--watch]
taskforge doctor     # checks DB connectivity, migration head, clock skew, stale workers
```
The CLI and the HTTP API both call **one service layer** (`taskforge.admin`), which fixes the duplication in H7.

---

## 7. Dashboard v2

### 7.1 Packaging and security
- Optional extra: `pip install "taskforge-queue[dashboard]"`.
- It's an **ASGI sub-app** you mount in your own app, or run standalone via `taskforge dashboard`.
- **Auth is required** unless you pass `--insecure-no-auth`. Supported: HTTP Basic, a static bearer token, or a callable `auth(request) -> bool` for SSO integration. There's also a `read_only=True` mode.
- CSRF protection on mutating endpoints. CORS is off by default.
- Assets (htmx, plus Alpine, uPlot and icons if adopted) are **vendored** into `static/`. No CDN.
- Optional payload redaction (`redact_keys=["password","token"]`), and tracebacks are hidden in read-only mode.

### 7.2 Pages
| Page | Content |
|---|---|
| **Overview** | KPI tiles (queued, running, failed/min, dead, active workers); throughput (succeeded/failed per minute, last 1 h/24 h); latency (wait time and run time p50/p95); queue-depth trend. All come from `job_events`, so there's no Prometheus dependency. |
| **Queues** | Per queue: depth, oldest pending age, throughput, error rate; pause/resume; concurrency limit. |
| **Jobs** | Cursor-paginated, filterable table (status, queue, task, time range, full-text on args); bulk retry/cancel/delete. |
| **Job detail** | Args, result, attempt timeline (from events), each attempt's traceback, worker, timings, "retry now" / "clone & edit". |
| **Workers** | Host, pid, queues, concurrency, current jobs, last heartbeat, version; stale workers are flagged. |
| **Dead letter** | Grouped by task and error type; "retry all matching". |
| **Schedules** | Cron, next run, last run status, enable/disable, run now. |

### 7.3 Live updates
Server-Sent Events (`/events`) push counters and job-state changes, backed by `LISTEN/NOTIFY`. Polling is the fallback. No WebSocket dependency.

### 7.4 REST API (versioned `/api/v1`)
It mirrors the admin service: `GET /queues`, `POST /queues/{name}/pause`, `GET /jobs?cursor=…`, `GET /jobs/{id}`, `POST /jobs/{id}/retry`, `POST /jobs/{id}/cancel`, `DELETE /jobs/{id}`, `GET /workers`, `GET /stats/timeseries?metric=&window=`, `GET /schedules`. Errors return proper status codes, never a silent `[]`. The OpenAPI schema is published in the docs.

---

## 8. Observability

- **Prometheus**: keep the per-worker exporter on `main` for *process* metrics (`jobs_processed_total`, duration histogram) and make the port configurable, defaulting to a free port such as `9464` instead of Prometheus's own 9090 (B9). Move *DB-derived* gauges (`taskforge_queue_depth{queue,status}`, `taskforge_oldest_pending_seconds{queue}`, `taskforge_workers{status}`) out of the workers into **one** custom `Collector` that queries the DB at scrape time. It's served by the dashboard at `/metrics` or by `taskforge metrics`, which fixes the per-worker duplication and stale values (B10). Actually increment `jobs_enqueued_total` (B11). Keep the `taskforge_` prefix and **no `worker_id`/`job_id` labels** (cardinality).
- **Grafana**: ship `deploy/grafana/taskforge.json` (overview, per-queue, errors) and document the import.
- **OpenTelemetry (extra `[otel]`)**: a span per job execution, with trace context propagated from enqueue to execution through a `trace_parent` stored with the job.
- **Logging**: the library only calls `logging.getLogger("taskforge.*")` and never configures handlers. The **CLI** configures logging (`--log-format text|json`, `--log-level`). JSON records keep the current field names (`job_id`, `task`, `queue`, `attempt`, `worker_id`, `event`).
- **Error trackers**: a documented Sentry hook recipe.

---

## 9. Packaging

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[project]
name = "taskforge-queue"            # D1
dynamic = ["version"]               # from git tag via hatch-vcs
requires-python = ">=3.10"
dependencies = ["SQLAlchemy>=2.0", "alembic>=1.12", "croniter>=2"]

[project.optional-dependencies]
postgres  = ["psycopg[binary]>=3.1"]
dashboard = ["fastapi>=0.110", "uvicorn>=0.29", "jinja2>=3.1"]
metrics   = ["prometheus-client>=0.19"]
otel      = ["opentelemetry-api>=1.20"]
cli       = ["typer>=0.12", "rich>=13"]     # or fold into core deps
all       = ["taskforge-queue[postgres,dashboard,metrics,otel,cli]"]

[project.scripts]
taskforge = "taskforge.cli:app"
```
- `src/taskforge/py.typed`. Static assets, templates and Alembic migrations are included in the wheel.
- The dashboard stays on FastAPI, which is already used and gives OpenAPI plus the existing Pydantic schemas, but **only in the `dashboard` extra**. `python-multipart` is dropped unless a form needs it.
- The minimal public surface is re-exported from `taskforge/__init__.py`: `TaskForge`, `Retry`, `Abort`, `JobContext`, `JobStatus`, `__version__`.

---

## 10. Quality bar

| Area | Standard |
|---|---|
| Formatting / lint | **ruff** (`ruff format` replaces black; rules: `E,F,I,B,UP,SIM,RUF,D` with Google docstrings on the public API) |
| Types | **mypy --strict** on `src/taskforge` (tests excluded at first) |
| Docstrings | Every public class and function: summary, Args, Returns, Raises, Example. Comments explain *why* (locking, ordering, races), not *what*. |
| Tests | pytest + pytest-xdist; **real Postgres** via a CI service container (and `testcontainers` locally); SQLite only for pure-unit tests. Coverage ≥ 85% on core, reported to Codecov. Property tests (hypothesis) for the state machine; a stress test (N workers × M jobs, assert exactly-once completion and no stuck jobs); a chaos test (kill -9 a worker mid-job, assert the reaper recovers it). |
| Safety | The test fixture refuses to run unless the DB name contains `test` (fixes B2). |
| Pre-commit | ruff, ruff-format, mypy, end-of-file, trailing whitespace, check-toml/yaml |
| Commits | Conventional Commits (already in use), enforced in CI on PR titles |

---

## 11. CI/CD (GitHub Actions)

| Workflow | Trigger | Jobs |
|---|---|---|
| `ci.yml` | PR, push to main | **lint** (ruff, mypy) → **test** matrix: Python 3.10–3.13 × Postgres 13, 15, 17 (service container) + SQLite unit set, Ubuntu + Windows (unit) → **coverage** upload → **build** (`python -m build`, `twine check`, install the wheel in a clean venv and run `taskforge --help` + a smoke test that the dashboard serves `/` and its static files) |
| `docs.yml` | PR (build only), main (deploy `dev`), tag (deploy version + `latest`) | `mkdocs build --strict`, link check, deploy via `mike` to GitHub Pages |
| `release.yml` | Tag `v*` | Build sdist + wheel → publish to **TestPyPI**, then **PyPI via Trusted Publishing (OIDC, no tokens)** → GitHub Release with changelog notes → build and push `ghcr.io/b1ca16/taskforge` Docker image (worker + dashboard) |
| `release-please.yml` | push to main | Opens and maintains a release PR that bumps the version and updates `CHANGELOG.md` from Conventional Commits |
| Dependabot | weekly | pip + GitHub Actions |
| CodeQL | weekly + PR | Python security scanning |

Branch protection on `main`: CI green + 1 review (or self-review while solo) + squash merges with Conventional Commit titles.

---

## 12. Documentation website

**Stack**: MkDocs Material + mkdocstrings (API reference from docstrings) + mkdocs-typer (CLI reference) + mike (versions) + a Mermaid diagram of the job lifecycle. It's hosted on GitHub Pages.

**Information architecture** (Diátaxis):
```
Home (landing: pitch, 20-second code sample, feature grid, "why Postgres")
Getting started
  ├─ Installation
  ├─ Quickstart (5 minutes: docker compose up → first job → dashboard)
  └─ Tutorial: add background jobs to a FastAPI app
Concepts
  ├─ Jobs, queues, workers
  ├─ Job lifecycle & state machine (diagram)
  ├─ Guarantees: at-least-once, idempotency, ordering
  ├─ How locking works (SKIP LOCKED, LISTEN/NOTIFY, heartbeats)
  └─ Retries & backoff
How-to guides
  ├─ Transactional enqueue with SQLAlchemy / Django ORM
  ├─ Scheduled & periodic jobs
  ├─ Priorities, rate limits, unique jobs
  ├─ Timeouts & cancellation
  ├─ Testing code that enqueues jobs (eager mode, fixtures)
  ├─ Deploying: Docker, docker-compose, systemd, Kubernetes (Helm snippet)
  ├─ Monitoring with Prometheus & Grafana
  ├─ Securing the dashboard
  └─ Migrating from Celery / RQ
Reference
  ├─ Python API (auto)
  ├─ CLI (auto)
  ├─ Configuration (all settings + env vars)
  ├─ REST API (OpenAPI)
  ├─ Database schema
  └─ Metrics
Project
  ├─ Comparison with alternatives (honest)
  ├─ Roadmap
  ├─ Changelog
  └─ Contributing
```

---

## 13. README (target structure, ≤ 1 screen before the fold)

1. Logo + one-line pitch + badges (PyPI version, Python versions, CI, coverage, docs, license, downloads)
2. A 15-line code sample: define → enqueue → `taskforge worker`
3. A dashboard screenshot/GIF
4. Features (6–8 bullets, each true today)
5. Install: `pip install "taskforge-queue[postgres,dashboard]"`
6. Links: Docs · Quickstart · Examples · Changelog · Contributing
7. Status: "Alpha. The API may change before 1.0"
8. License

Everything else (CLI reference, API, metrics lists) moves to the docs site.

---

## 14. Repository layout (target)

```
.github/            workflows/, ISSUE_TEMPLATE/, PULL_REQUEST_TEMPLATE.md, dependabot.yml
deploy/             docker/Dockerfile, docker-compose.yml (pg + worker + dashboard + prometheus + grafana), grafana/
docs/               mkdocs site (revamp/ docs move to docs/project/ or get archived)
examples/           fastapi_app/, django_app/, flask_app/, scripts/ (replaces demo_client/)
src/taskforge/
  __init__.py       public API re-exports, __version__
  app.py            TaskForge
  config.py         Settings
  task.py           @job decorator, Task, JobHandle
  context.py        JobContext
  exceptions.py     Retry, Abort, TaskForgeError…
  retry.py          RetryPolicy strategies
  models.py         SQLAlchemy models
  backends/         postgres.py (claim/notify), sqlite.py (dev only)
  migrations/       alembic env + versions
  worker/           worker.py, pool.py, reaper.py, supervisor.py, signals.py
  admin.py          service layer shared by CLI + API
  scheduler.py      periodic jobs
  cli/              typer app
  dashboard/        FastAPI app, api, schemas, templates/, static/ (vendored)
  metrics/          prometheus collector, otel
  contrib/          fastapi.py, django/, flask.py
  testing.py        eager mode, pytest fixtures (pytest plugin entry point)
tests/              unit/, integration/ (postgres), e2e/
benchmarks/
CHANGELOG.md  CONTRIBUTING.md  CODE_OF_CONDUCT.md  SECURITY.md  LICENSE  README.md
```

---

## 15. Community & project hygiene
- `CONTRIBUTING.md` (dev setup in 3 commands: `uv sync`, `docker compose up -d db`, `pytest`), `CODE_OF_CONDUCT.md` (Contributor Covenant), `SECURITY.md` (private disclosure via GitHub advisories).
- Issue templates (bug / feature / question) and a PR template with a checklist.
- Labels: `good first issue`, `help wanted`, `area:*`, `breaking`.
- GitHub Discussions for Q&A.
- A public roadmap as a GitHub Project board generated from [03-PRIORITIES.md](03-PRIORITIES.md).
- `uv` as the recommended dev workflow (`uv.lock` committed for dev only; library deps stay as ranges).

---

## 16. Success metrics
- **Correctness**: zero known stuck-job scenarios; the chaos test is green in CI.
- **DX**: from `pip install` to the first job processed in under 5 minutes, following the Quickstart verbatim (test it with someone who has never seen the project).
- **Performance**: a published benchmark (jobs/s, p95 pickup latency) on a documented setup.
- **Adoption signals**: PyPI downloads/month, GitHub stars, first external contributor, first external issue.
