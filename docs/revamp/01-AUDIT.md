# TaskForge — Current-State Audit

_Audit date: 2026-09-25_
_**Baseline: `origin/main` @ `f3f0ad0`** (Apr 22 2026). The local clone was one commit behind. Its uncommitted changes (`web/`, `monitoring/`, …) are an older, abandoned experiment and are **not** audited here, except where noted in §7._

## TL;DR

TaskForge has a sound core: a Postgres queue using `SKIP LOCKED`, retries with backoff, a dead-letter state, workers registered in the DB with heartbeats, per-worker Prometheus metrics, job tags, and a server-rendered HTMX dashboard. It has 65 tests. The architecture choices are the right ones.

**It is not yet shippable as a library.** Here's why:
- `pyproject.toml` says **1.0.0 / Production/Stable**.
- The wheel **doesn't include the dashboard templates**, so the dashboard 404s after `pip install`.
- The PyPI name `taskforge` **is taken**.
- Importing the package **hijacks the host app's logging** and **requires a DB URL at import time**.
- A crashed worker leaves its jobs **stuck in `running` forever**. Heartbeats exist, but nothing acts on them.
- The dashboard is **unauthenticated** and bound to `0.0.0.0` with `reload=True`.

Every one of these is fixable in days, not weeks.

---

## 1. Inventory (origin/main)

| Area | Files | State |
|---|---|---|
| Models | `task_queue/models.py` | `Queue`, `Job` (+ `tags` JSON, `started_at`, `completed_at`), `WorkerRecord` (hostname, pid, queues, heartbeat), `JobStatus`, `WorkerStatus`. String UUID PKs, naive `DateTime`. Indexes on `status`, `type`, `created_at`. |
| Enqueue | `task_queue/db.py` | `enqueue_single_job(type, payload, queue_name, max_attempts, scheduled_at, tags)`. Opens its own session and auto-creates queues. |
| Registry / Executor | `jobs/registry.py`, `worker/executor.py` | Global dict + `@register`. dict→kwargs, list→args, `logger` injection. |
| Worker | `worker/worker.py` | Single-threaded poll loop; DB registration/deregistration; heartbeat thread (15 s); metrics refresh thread (10 s); Prometheus HTTP server on :9090; backoff `10·2^n`. |
| Metrics | `metrics/collectors.py`, `metrics/server.py` | `taskforge_jobs_processed_total{queue,job_type,status}`, `taskforge_job_execution_duration_seconds`, `taskforge_queue_depth{queue,status}`, `taskforge_active_workers{queue}`, `taskforge_worker` info. |
| Dashboard | `dashboard/app.py`, `api.py`, `schemas.py`, `templates/*` | FastAPI + Jinja2 + HTMX. Pages: overview (5 s auto-refresh), jobs (filters, pagination), job detail (replay). JSON API: `/api/overview`, `/api/jobs` (tag filters), `/api/jobs/{id}`, `/api/jobs/{id}/replay`, `/api/workers`, `/api/queues`. Pydantic response models. |
| CLI | `cli/main.py` | argparse: `dead-letter`, `stats`, `history` (incl. tags), `replay`, `workers`. Output goes through the logger. |
| Config | `config/settings.py`, `config/logging.py`, `db/base.py` | Env vars only (`DATABASE_URL`, `DEFAULT_MAX_ATTEMPTS`). |
| Docs | `README.md`, `ROADMAP.md` (Phases 0–11), `TESTING_STRATEGY.md`, `docs/architecture.md`, `docs/DOCKER_PG_SETUP.md` | Well written; several claims are out of date or untrue (§4). |
| Tests | 11 files, 65 tests | Dashboard API tests via TestClient; worker registration; tags; metrics. |
| Tooling | `[project.optional-dependencies] dev = [pytest, httpx]` | No CI, lint config beyond `[tool.black]`, type checking, pre-commit, or changelog. |

**Test run (SQLite, Python 3.13, clean venv): 58 passed, 7 failed.** All 7 failures come from the Postgres-only claim SQL or SQLite not enforcing FKs. They should pass on Postgres, but I couldn't verify that because Docker isn't running on this machine.

---

## 2. Correctness bugs

Severity: 🔴 breaks core behaviour / data · 🟠 wrong results or bad failure mode · 🟡 latent.

| # | Sev | Where | Problem |
|---|---|---|---|
| B1 | 🔴 | `worker/worker.py` `_process_job` | **Stuck jobs.** If the worker process dies (kill -9, OOM, deploy) or the post-execution `commit` fails (e.g. a non-JSON-serialisable return value), the job stays `running` and locked **forever**. Heartbeats are recorded, and the dashboard *displays* "lost" after 60 s, but **nothing reclaims the lost worker's jobs**. `architecture.md` says jobs are reclaimed after a lock timeout. |
| B2 | 🔴 | `tests/conftest.py` | The fixture runs `drop_all()` on **whatever `DATABASE_URL` points to**. Running `pytest` with a real DB configured wipes it. |
| B3 | 🔴 | `task_queue/test_db.py` | **Ships in the wheel** (verified) and **drops all tables on import**. |
| B4 | 🟠 | `worker/worker.py` `run()` | `time.sleep(1)` runs after *every* iteration, even right after processing a job. That caps throughput at about 1 job/s per worker. |
| B5 | 🟠 | `worker/worker.py` | `max_concurrency=10` is accepted but never used. One job at a time. |
| B6 | 🟠 | `worker/worker.py` `run()` / `stop()` | No signal handling. `SIGTERM` (Docker, systemd, K8s) kills the process without `_deregister()` or draining. Combined with B1, **every deploy can strand a job**. |
| B7 | 🟠 | `models.py` + claim SQL | Naive `DateTime` columns; Python writes aware UTC, SQL compares with `NOW()` (server local time). On a non-UTC Postgres, scheduled/retried jobs run hours early or late. The `_ensure_aware()` helpers in the dashboard work around the symptom. |
| B8 | 🟠 | `models.py`, `worker.py`, `dashboard/*` | `datetime.UTC` needs Python ≥ 3.11, but `requires-python = ">=3.10"`. It crashes on 3.10. |
| B9 | 🟠 | `metrics/server.py` | Default metrics port **9090 is Prometheus's own default port**. A second worker *process* on the same host crashes with `OSError: address in use`. No `--metrics-port` in any CLI. |
| B10 | 🟠 | `worker/worker.py` `_refresh_queue_depth` | **Every** worker publishes `taskforge_queue_depth` for **all** queues, so `sum()` in Grafana multiplies depth by the number of workers. A status that drops to 0 keeps its last non-zero value, because the gauge is never reset. |
| B11 | 🟠 | `metrics/collectors.py` | `taskforge_jobs_enqueued_total` is defined but never incremented. |
| B12 | 🟠 | `dashboard/api.py` `replay_job`, `cli/main.py` | Replay creates a **new** job but leaves the original `dead` with no link between them. Replaying the same job twice runs it twice, and the dead list never shrinks. |
| B13 | 🟠 | `task_queue/db.py` | Get-or-create queue races: two producers enqueueing to a new queue concurrently raise `IntegrityError`. |
| B14 | 🟠 | worker | The `failed` status is never assigned (retries go straight to `pending`), yet the dashboard, CLI and API all count and filter on it. |
| B15 | 🟡 | claim SQL / models | There's no composite index for the claim query (`status, queue_id, scheduled_at, created_at`). It seq-scans as `jobs` grows, and nothing ever prunes finished jobs. |
| B16 | 🟡 | `worker/executor.py` | `kwargs = payload; kwargs["logger"] = ...` mutates `job.payload` in place. |
| B17 | 🟡 | `jobs/registry.py` | A duplicate `@register` name silently replaces the earlier function. |
| B18 | 🟡 | `models.py` | `payload`/`tags` are `JSON`, not `JSONB`, so tag filters can't use a GIN index on Postgres. |
| B19 | 🟡 | `test_db_models.py::test_job_requires_valid_queue` | Fails on SQLite: `PRAGMA foreign_keys=ON` is never enabled. |

---

## 3. Library hygiene (why it can't be embedded yet)

| # | Problem | Impact |
|---|---|---|
| H1 | `db/base.py` creates the engine **at import time** and raises if `DATABASE_URL` is unset. It also calls `load_dotenv()` on import. | You can't `import taskforge`, run `--help`, or build API docs without a DB. Loading `.env` silently changes the host app's environment. |
| H2 | `setup_logging()` runs on import in `config/logging.py`, `worker.py`, `executor.py`, `cli/main.py`, and **clears the root logger's handlers**. | Importing TaskForge into a Django/FastAPI app destroys the host app's logging. This is a deal-breaker for a library. |
| H3 | Only a global engine and a global registry. | One DB per process; hard to test in isolation. |
| H4 | Enqueue opens its **own** session and commits. | You lose the main advantage of a DB queue: *transactional enqueue*. |
| H5 | FastAPI, uvicorn, jinja2, python-multipart and prometheus-client are **hard** dependencies. | Anyone who only wants a queue pulls in a web stack. |
| H6 | The dependency is `psycopg[binary]` (v3), but `DOCKER_PG_SETUP.md` uses `postgresql+psycopg2://`. | Following the guide fails with `ModuleNotFoundError: psycopg2`. |
| H7 | Replay, stats and worker-status logic are duplicated between `cli/main.py`, `dashboard/app.py` and `dashboard/api.py` (`_ensure_aware` and the "lost if > 60 s" rule are copy-pasted). | Fixes land in one place and not the others. |
| H8 | Sparse type hints, no `py.typed`. | No editor completion or mypy support for users. |
| H9 | There's no worker entry point. Users write their own `run_worker.py` with `sys.path` hacks (see `demo_client/`). | This is the first thing a new user hits. |

---

## 4. Docs vs. reality

| Claim | Where | Reality |
|---|---|---|
| "Tests use an in-memory SQLite database" | `TESTING_STRATEGY.md` | Tests use `DATABASE_URL`, and the worker only works on Postgres. |
| "Jobs can be reclaimed after a lock timeout" | `architecture.md` | Not implemented (B1). |
| "Phase 5 ✅ COMPLETED — prioritisation, cron, plugin system, distributed workers" | `ROADMAP.md` | Priorities, cron and plugins don't exist. Phase 8 even says it "enhances Phase 5's basic prioritisation". |
| "Not yet packaged for PyPI", `pip install -r requirements.txt`, `your-username` URL | `README.md` | No requirements.txt; placeholder URL; the dashboard/metrics/tags features aren't documented in the README at all. |
| "Development Status :: 5 - Production/Stable", 1.0.0 (also `FastAPI(version="1.0.0")`) | `pyproject.toml`, `dashboard/app.py` | Alpha. |
| Last commit message "schedule conflicts, instructor notes, phone, bulk attendance…" | git history | Wrong message (from another project). It actually added the dashboard, metrics, worker registry and tags. Worth noting in the CHANGELOG, since history can't be rewritten on a pushed `main` without force-pushing. |

---

## 5. Packaging & distribution

- **The PyPI name `taskforge` is taken** (an unrelated taskwarrior plugin, v0.1.1). `task-forge`, `taskforge-queue` and `pytaskforge` were free on 2026-09-25.
- **Templates aren't packaged** (verified by building the wheel: zero `.html` files). `static/` only contains `.gitkeep`.
- No `[build-system]` table; builds via the setuptools fallback.
- No `[project.scripts]`: no `taskforge` command, no `taskforge worker`, no `taskforge dashboard`.
- No migrations. `WorkerRecord`, `tags`, `started_at` and `completed_at` were added via `create_all`, which won't alter existing tables. **Anyone with a DB from the previous version already has a broken schema.**

## 6. Security

- The dashboard and API have **no authentication**. `POST /api/jobs/{id}/replay` re-runs arbitrary jobs (emails, payments…) with no auth or CSRF protection.
- `run_dashboard.py` binds **`0.0.0.0` with `reload=True`**, a dev server exposed on all interfaces.
- `/api/jobs/{id}` returns payloads, results and full tracebacks verbatim (these can contain secrets/PII). There's no redaction.
- HTMX is loaded from `unpkg.com` at runtime, so the dashboard breaks offline/air-gapped and can't have a strict CSP. There's no SRI hash either.
- `/docs` (Swagger UI) is exposed by default.

## 7. Repo hygiene

- **Local clone**: one commit behind `origin/main`, with a conflicting uncommitted experiment (`src/taskforge/web/`, `src/taskforge/monitoring/`, modified `worker.py`/`cli/main.py`/`db.py`/`pyproject.toml`/`README.md`, `scripts/init_db.py`, `tests/test_cli_enhanced.py`, `tests/test_metrics.py`) plus a stray `=0.19.0` file (pip output from an unquoted `>=`). The remote version supersedes it: it has the same ideas, better executed (Jinja/HTMX instead of a 1,750-line single HTML page; per-worker metrics server instead of an unreachable in-process registry). **Recommendation:** park it on a branch (`git switch -c archive/web-experiment && git add -A && git commit -m "wip: old dashboard experiment"`), then `git switch main && git pull`. The experiment also contains one thing worth salvaging: the `cancel` command.
- `commands.txt`, `FOLDER_STRUCTURE.txt` (outdated), empty `scripts/dev.py` and empty `utils/` package. Add `.env.example`.

## 8. What's genuinely good (keep it)

- The claim query `UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED) RETURNING`, the same pattern as Oban, GoodJob, River and Procrastinate.
- **Worker registry + heartbeats already exist**, so a stale-job reaper is a small step away.
- **Per-worker Prometheus exporter** with `taskforge_`-prefixed, low-cardinality metrics (no `job_id` labels).
- **Server-rendered HTMX dashboard** with Pydantic API schemas: no Node toolchain, easy to package, easy to mount.
- **Tags** on jobs, filterable in API/CLI/dashboard.
- Clear Registry / Executor / Worker separation, structured JSON logging with per-job context, and honest at-least-once guarantees.
- A thorough, well-structured ROADMAP and a real test suite, including a concurrency test and dashboard API tests.
- Conventional-commit history, which makes automated changelogs easy.
