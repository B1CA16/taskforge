# TaskForge — Priorities & Milestones

_2026-09-25 · Ordered plan to get from [the current state](01-AUDIT.md) to [the spec](02-SPEC.md)._

**Guiding rule:** *correct → installable → operable → delightful.* Don't build features on top of a red test suite, and don't publish until a stranger can install it and it works.

Priority key: **P0** do first, blocks everything · **P1** needed for the first public release · **P2** makes it production-worthy · **P3** differentiators / growth.
Size: S ≈ < ½ day · M ≈ 1–3 days · L ≈ 1–2 weeks.

---

## Milestone 0: Save the work & stop the bleeding (P0, ~1 week)

Goal: green tests, no data-destroying or silently-wrong behaviour, and an honest version number.

> **Status (2026-09-26): ✅ done on branch `chore/m0-stabilize`.** 90/90 tests pass on Postgres 17 (Python 3.13 on Windows, Python 3.10 on Linux). See `CHANGELOG.md`.
> Still open from M0: reserving the PyPI name (0.3, needs your PyPI account). Pulled forward from M1: the `init-db` command, graceful shutdown, and binding the demo dashboard to 127.0.0.1.

| # | Task | Fixes | Size |
|---|---|---|---|
| 0.1 | Park the old local experiment on `archive/web-experiment`, then `git pull` so the local `main` matches `origin/main`. Salvage its `cancel` command idea. Delete `=0.19.0`, `commands.txt`, `FOLDER_STRUCTURE.txt`, empty `scripts/dev.py`, and **`task_queue/test_db.py`** (it ships and drops tables, B3). Add `.env.example`. | §7, B3 | S |
| 0.2 | Set the version to `0.2.0.dev0` and `Development Status :: 3 - Alpha`. | D2 | S |
| 0.3 | **Decide the PyPI name** (recommended: `taskforge-queue`) and reserve it on PyPI and TestPyPI. | D1 | S |
| 0.4 | Make the test fixture safe: refuse to run unless the DB name contains `test`. Add `docker-compose.yml` with a `postgres:17` test DB. Make Postgres the default test target. | B2 | S |
| 0.5 | Fix the quick bugs: `datetime.UTC`→`timezone.utc` for 3.10 (B8); make the metrics port configurable and not 9090 (B9); stop per-worker `queue_depth` and reset stale gauges (B10); increment `jobs_enqueued_total` (B11); don't mutate the payload (B16); raise on duplicate registration (B17); enable the SQLite FK pragma (B19). | B8–B11, B16, B17, B19 | S |
| 0.6 | Remove import-time side effects: lazy engine creation (H1), and **delete every `setup_logging()` call from library modules**, calling it only from CLI entry points (H2). | H1, H2 | M |
| 0.7 | Worker: only sleep when no job was found (B4). Handle SIGTERM/SIGINT: finish the current job, deregister, exit (B6). If the post-execution commit fails, mark the job failed in a fresh transaction instead of leaving it `running` (B1, partial). Replay should mark the original job as replayed and link it to the new one (B12). | B1, B4, B6, B12 | M |
| 0.8 | Switch to `timestamptz` columns and compare with DB `now()` consistently (B7), which removes the `_ensure_aware` hacks. Add the composite claim index (B15). Use a real `failed` state, or drop it from the UI (B14). | B7, B14, B15 | S |
| 0.9 | Fix the docs that currently lie: `TESTING_STRATEGY.md` (Postgres), `architecture.md` (no reclaim yet), `ROADMAP.md` Phase 5 "completed", README placeholders. | §4 | S |

**Exit criteria:** `pytest` is 100% green on Postgres 17 and Python 3.10 + 3.13. Importing `taskforge` in a fresh interpreter with no env vars works and doesn't touch logging.

---

## Milestone 1: Installable & professional foundation → release `0.2.0` (P1, ~2–3 weeks)

Goal: `pip install taskforge-queue` works for a stranger, CI guards every change, and the README sells it honestly.

| # | Task | Spec § | Size |
|---|---|---|---|
| 1.1 | **Packaging**: hatchling + hatch-vcs, extras (`postgres`, `dashboard`, `metrics`, `cli`), package data (static, **templates: missing from the wheel today, so the installed dashboard 404s**, migrations), `py.typed`, `[project.scripts] taskforge`. | 9 | M |
| 1.2 | **`TaskForge` app object + `@tf.job` + `.enqueue()`**, with deprecated shims for `register` / `enqueue_single_job`. Config from args → env → defaults. | 3.1–3.2 | L |
| 1.3 | **Transactional enqueue** (`_session=`). It's the headline feature, so do it early. | 3.2 | S |
| 1.4 | **Alembic migrations** shipped in the package, plus `taskforge db upgrade`. Schema v2 (at least: prefixed tables, `timestamptz`, `run_at`, `priority`, `heartbeat_at`, `last_error` jsonb). | 4 | M |
| 1.5 | **CLI v1** on Typer + Rich: `worker`, `db`, `jobs`, `dead`, `queues`, `workers`, `stats`, `dashboard`. Extract the `admin.py` service layer shared with the dashboard and API (H7). | 6 | M |
| 1.6 | **Tooling**: ruff (lint + format), mypy, pre-commit, Conventional Commit PR-title check. | 10 | S |
| 1.7 | **CI**: `ci.yml` (lint, test matrix with a Postgres service, build + install-from-wheel smoke test), Codecov, Dependabot. | 11 | M |
| 1.8 | **Release pipeline**: release-please + `release.yml` with PyPI Trusted Publishing (TestPyPI first). | 11 | S |
| 1.9 | **README rewrite** per spec §13, plus `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, issue/PR templates. | 13, 15 | M |
| 1.10 | **Docstrings & comments pass** on the public API (Google style) and on the tricky parts (claim query, state transitions): *why*, not *what*. | 10 | M |
| 1.11 | Replace `demo_client/` with `examples/quickstart/` + `docker-compose.yml` (pg + worker + dashboard). | 14 | S |
| 1.12 | **Dashboard hardening only** (not the redesign yet): move it to an extra; require token/basic auth, especially on `POST /replay`; bind `127.0.0.1` by default, no `reload`; vendor htmx; hide `/docs` unless enabled; optional payload redaction. | 7.1 | M |

**Exit criteria:** the tag `v0.2.0` is published to PyPI by CI. A fresh `pip install "taskforge-queue[postgres,dashboard]"` plus the README quickstart works on Linux, macOS and Windows.

---

## Milestone 2: Production-grade worker → `0.3.0` (P2, ~3 weeks)

Goal: you can trust it with real traffic. Nothing gets stuck, it scales, and shutdown is clean.

| # | Task | Spec § | Size |
|---|---|---|---|
| 2.1 | **Stale-job reaper** on top of the existing worker registry and heartbeats: mark silent workers `lost` in the DB (today that only happens in the UI) and requeue or kill their jobs. Closes B1. | 5 | S |
| 2.2 | **Concurrency** (thread pool, batch claim `LIMIT n`) and **async job support**. | 5 | L |
| 2.3 | **LISTEN/NOTIFY** wake-ups with a poll fallback. | 5 | M |
| 2.4 | **Graceful shutdown** (SIGTERM drain, release on timeout, Windows support). | 5 | M |
| 2.5 | **Retry policies** (`exponential` + jitter, `linear`, `fixed`, custom), `Retry(after=)`, `Abort`, `retry_on`. | 3.3, 5 | M |
| 2.6 | **Job timeouts** (soft/hard) and **cooperative cancellation** via `JobContext`. | 3.3, 5 | M |
| 2.7 | **Priorities** and **unique jobs** (`_unique_key`). | 3.2, 4 | S |
| 2.8 | **Retention / prune** command + optional auto-prune. | 4 | S |
| 2.9 | Test suite additions: stress (exactly-once under N workers), chaos (kill -9 → recovered), hypothesis state-machine tests. | 10 | M |
| 2.10 | **Benchmark** script + a first published number. | 16 | S |

---

## Milestone 3: Dashboards, observability & docs site → `0.4.0` (P2, ~3 weeks)

Goal: operators can *see* what's happening, and newcomers can learn it without reading source.

| # | Task | Spec § | Size |
|---|---|---|---|
| 3.1 | `job_events` table + time-series stats queries (single aggregated SQL, not N+1). | 4, 7.2 | M |
| 3.2 | **Dashboard v2**, extending the existing overview / jobs / job-detail pages: throughput and latency charts (p50/p95), a Queues page (pause/resume), a Workers page, bulk actions, an attempt timeline in job detail, tag facets, and dead-letter grouping by error. | 7.2 | L |
| 3.3 | **SSE live updates** + a mountable ASGI app (`contrib.fastapi.mount_dashboard`). | 7.3, 3.5 | M |
| 3.4 | Versioned **REST API `/api/v1`** with OpenAPI. | 7.4 | M |
| 3.5 | **Prometheus split**: keep the per-worker exporter for process metrics; add one DB-backed collector for queue depth, oldest-pending age and worker counts. | 8 | M |
| 3.6 | **Grafana dashboard JSON** + a compose stack with Prometheus & Grafana preconfigured. | 8 | S |
| 3.7 | **Docs website**: MkDocs Material + mkdocstrings + mike on GitHub Pages; landing page, Quickstart, Concepts (with the lifecycle diagram), How-tos, Reference. `docs.yml` workflow. | 12 | L |
| 3.8 | Screenshots/GIF of the dashboard for the README and landing page. | 13 | S |

---

## Milestone 4: Scheduling & ecosystem → `0.5.0` (P3)

| # | Task | Size |
|---|---|---|
| 4.1 | **Periodic jobs** (`@tf.periodic(cron=…)`), schedules table, dashboard page. | M |
| 4.2 | **Framework integrations**: FastAPI, Django (management command + settings), Flask. | M |
| 4.3 | **Testing helpers**: eager mode, a pytest plugin with a `taskforge` fixture, `assert_enqueued(...)`. | M |
| 4.4 | **Queue-level rate limits and concurrency limits** (token bucket stored in Postgres). | M |
| 4.5 | **Chains & groups** (`a.then(b)`, `group([...]).then(c)`) via `parent_id`. Keep it simple, no DAGs. | L |
| 4.6 | **OpenTelemetry** tracing extra; a Sentry recipe. | S |
| 4.7 | **Docker image** on GHCR + a Helm/K8s example; "Migrating from Celery/RQ" guide. | M |

---

## Milestone 5: `1.0.0` (P3)
- Freeze and document the public API; deprecations removed.
- At least 3 external users/issues, the docs Quickstart validated by someone new.
- A security review of the dashboard; `SECURITY.md` process exercised.
- `Development Status :: 5 - Production/Stable`.

---

## Ideas backlog (unprioritised, pick later)
- **Webhooks** on job completion/failure (a job type itself, so it gets retries for free).
- **Circuit breaker** per task: auto-pause a task after N consecutive failures and alert.
- **Job result backend API** + `JobHandle.result(timeout=)` using NOTIFY.
- **Encrypted args** (Fernet key in config) for PII payloads.
- **Multi-tenant** `tenant_id` column + per-tenant fairness.
- **VS Code / PyCharm snippets**, `taskforge init` scaffolding command.
- **"Explain this failure"** in the dashboard: group dead jobs by exception fingerprint.
- **Batch jobs** (`@tf.job(batch_size=100)`) that receive many payloads at once.
- A **Terraform/Pulumi**-friendly health endpoint (`/healthz`, `/readyz`) for workers.

---

## Suggested immediate next 5 actions
1. Park the old local experiment on a branch, `git pull` `main`, and delete the stray files (0.1).
2. Pick the PyPI name and reserve it (0.3).
3. Spin up Postgres via compose and make the suite green (0.4, 0.5).
4. Rip out the import-time logging/engine side effects (0.6).
5. Add a minimal `ci.yml` right away so the suite *stays* green while everything else changes (pulling 1.7 forward).
