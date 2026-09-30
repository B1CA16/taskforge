# Contributing to TaskForge

Thanks for helping. This page covers the dev setup and the workflow. The detailed conventions live in two guides:

- [Code style](docs/contributing/code-style.md): Python formatting, naming, types, **docstring templates**, comments, errors, logging and tests.
- [Writing docs](docs/contributing/writing-docs.md): voice, Markdown formatting, commands, links and **page templates**.

## Development setup

You need Python 3.10+, Git and Docker (for the test database).

```bash
git clone https://github.com/B1CA16/taskforge.git
cd taskforge
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d test-db
pytest
```

```powershell
git clone https://github.com/B1CA16/taskforge.git
cd taskforge
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
docker compose up -d test-db
pytest
```

> [!WARNING]
> The test suite drops all tables. It refuses to run unless the database name contains `test`, and by default it uses the disposable database from `docker compose` (port 5436).

Install the Git hooks once, so formatting and lint run on every commit:

```bash
pre-commit install
```

CI runs these checks on every push. To run them yourself:

```bash
ruff format .
ruff check .
npx markdownlint-cli2 "**/*.md"
python scripts/check_links.py
pytest
```

CI also runs the tests on Python 3.10 to 3.14, Postgres 14 and 18, and Windows, and it checks that the built wheel installs and works (`scripts/check_wheel.py`).

## Workflow

1. **Open or pick an issue** for anything bigger than a typo, so the approach can be agreed before you write code.
2. **Branch from `main`**, named `<type>/<short-description>`: `fix/stale-lock-reaper`, `docs/quickstart`, `feat/priorities`.
3. **Keep PRs focused:** one change per PR. Refactors go in their own PR, separate from behavior changes.
4. **Update docs and `CHANGELOG.md`** in the same PR as the change (see [CHANGELOG entry](docs/contributing/writing-docs.md#changelog-entry)).
5. **Open the PR.** The template lists what reviewers check.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/). The release tooling reads them to pick the next version and write the changelog.

```text
<type>(<scope>): <summary>

<body: what changed and why, wrapped at 72 characters>

<footer: BREAKING CHANGE: ..., Closes #123>
```

- **Types:** `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`, `style`.
- **Scopes (optional):** `worker`, `queue`, `cli`, `dashboard`, `metrics`, `db`, `config`, `deps`.
- **Summary:** imperative mood, lowercase, no trailing period, 72 characters or fewer. For example, `fix(worker): record a failed attempt when saving the outcome fails`.
- **Breaking changes:** add `!` after the type or scope (`feat(queue)!: ...`), and explain the migration in a `BREAKING CHANGE:` footer.
- **The body explains why.** The diff already shows what.

## Reporting security issues

Please don't open a public issue. Use GitHub's [private vulnerability reporting](https://github.com/B1CA16/taskforge/security/advisories/new) instead.
