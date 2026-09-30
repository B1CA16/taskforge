# TaskForge: notes for AI coding assistants

TaskForge is a Postgres-backed background job queue for Python, published on PyPI as `taskforge-queue` (import name `taskforge`). The code is public, so everything you write is read by strangers.

## Follow the conventions

- Python code, docstrings, comments, errors, logging, tests: [docs/contributing/code-style.md](docs/contributing/code-style.md)
- Markdown, README, CHANGELOG: [docs/contributing/writing-docs.md](docs/contributing/writing-docs.md)
- Branches, commits and PRs: [CONTRIBUTING.md](CONTRIBUTING.md)

The short version:

- US English and the glossary terms (job, job type, handler, queue, worker, attempt, dead, replay).
- Google-style docstrings with full sections on the public API.
- Comments explain _why_; never restate the code.
- Update `CHANGELOG.md` with every user-visible change.

## Working on the code

- Tests need Postgres: `docker compose up -d test-db`, then `pytest`. The suite drops all tables and refuses databases whose name doesn't contain `test`. Never point it anywhere else.
- Before finishing, run `ruff format .`, `ruff check .` and `pytest`.
- The library must never configure logging or touch the database at import time.
- Plans and priorities: [docs/revamp/03-PRIORITIES.md](docs/revamp/03-PRIORITIES.md). The spec: [docs/revamp/02-SPEC.md](docs/revamp/02-SPEC.md).
