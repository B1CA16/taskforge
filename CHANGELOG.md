# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]: 0.2.0

Stabilization release (milestone M0 in [docs/revamp/03-priorities.md](docs/revamp/03-priorities.md)).

### ⚠️ Breaking

- **Distribution renamed to `taskforge-queue`** (`taskforge` is taken on PyPI). The import name is still `taskforge`.
- **Version reset from 1.0.0 to 0.2.0 (alpha).** The API will change before 1.0.
- **Timestamps are now `timestamptz`** (aware UTC). There are no migrations yet, so existing Postgres databases must be recreated: drop the tables, then run `python -m taskforge.cli.main init-db`.
- **Retries use the `failed` status** (waiting for the retry) instead of going back to `pending`.
- **The library no longer configures logging on import.** Call `taskforge.config.logging.setup_logging()` in your worker script (the CLI does it for you).
- Registering a _different_ function under an existing job name now raises `ValueError`.
- Requires SQLAlchemy 2.0+.
- The worker's Prometheus port default changed from 9090 (Prometheus's own port) to **9464**; override it with `TASKFORGE_METRICS_PORT`.
- Removed `taskforge.task_queue.test_db` (it dropped all tables when imported).

### Added

- `init-db` CLI command: creates missing tables and never drops anything.
- Graceful worker shutdown on Ctrl+C, SIGTERM and Ctrl+Break (Windows); the current job always finishes, and a second signal forces exit.
- `Worker(poll_interval=..., handle_signals=...)` options.
- `TASKFORGE_DATABASE_URL` setting (falls back to `DATABASE_URL`).
- `replay --force` CLI flag; replayed jobs are linked through the `taskforge.replayed_as` / `taskforge.replayed_from` tags.
- `docker-compose.yml` with a disposable Postgres for the test suite; `.env.example`.
- `taskforge.__version__`.

### Fixed

- The built wheel didn't include the dashboard templates, so an installed dashboard returned 404. The package now builds with hatchling and ships `templates/` and `static/`.
- Jobs whose outcome couldn't be saved (e.g. a non-JSON-serializable return value) were left in `running` forever.
- Workers slept 1 s after every job, capping throughput at about 1 job/s.
- Scheduled and retried jobs ran early or late when the Postgres server wasn't in UTC.
- Crashes on Python 3.10 (`datetime.UTC`).
- Importing TaskForge required a database URL and replaced the host application's logging handlers.
- The test suite dropped all tables of whatever `DATABASE_URL` pointed to. It now only runs against databases named `*test*`.
- A second worker on the same host crashed because the metrics port was in use; it now logs a warning.
- `taskforge_queue_depth` kept stale values after a status emptied; `taskforge_jobs_enqueued_total` was never incremented.
- Replaying the same dead job twice ran the work twice; it's now refused (CLI error / HTTP 409).
- `GET /api/jobs/{id}` returned 500 for jobs whose result wasn't a dict or list.
- Concurrent enqueues to a new queue could fail with `IntegrityError`.
- The executor mutated the stored job payload.
- SQLite didn't enforce foreign keys.

### Docs

- Applied the conventions to the existing code and docs: docstrings on the whole public API, comments that explain why, US spelling, sentence-case headings, and lint-clean Markdown. Docs were renamed to kebab-case: `ROADMAP.md` → `docs/roadmap.md`, `TESTING_STRATEGY.md` → `docs/contributing/testing.md`, `docs/DOCKER_PG_SETUP.md` → `docs/docker-postgres-setup.md`, and `docs/revamp/*` to lowercase. Update any bookmarks.
- Added contributor conventions: [code style](https://github.com/B1CA16/taskforge/blob/main/docs/contributing/code-style.md) (docstring templates, comments, errors, logging, glossary), [writing docs](https://github.com/B1CA16/taskforge/blob/main/docs/contributing/writing-docs.md) (voice, Markdown, page templates), `CONTRIBUTING.md` and a PR template. Ruff, EditorConfig and markdownlint are configured to match.
- README rewritten to match what exists today (PowerShell commands, config table, job states).
- Corrected claims in `docs/roadmap.md` (Phase 5 is partial), `docs/architecture.md` (no stale-lock reclamation yet), `docs/contributing/testing.md` (runs on Postgres), and `docs/docker-postgres-setup.md` (psycopg 3 URL).
- Added the audit, spec and priorities under `docs/revamp/`.

### Note on history

Commit `f3f0ad0` has an unrelated message ("schedule conflicts, instructor notes…"). It actually added the dashboard, Prometheus metrics, worker registration with heartbeats, and job tags.
