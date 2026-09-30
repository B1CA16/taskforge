# Code style

How TaskForge's Python code, docstrings and comments are written. This code is public, and people learn from it, copy it, and read it when something breaks at 3 a.m. Write for that reader.

Most rules here are enforced by [Ruff](https://docs.astral.sh/ruff/) (`ruff check` and `ruff format`, configured in `pyproject.toml`). Where a rule can't be automated, it's marked _(review)_ and checked in code review.

## Contents

- [Language](#language)
- [Formatting](#formatting)
- [Naming](#naming)
- [Type hints](#type-hints)
- [Docstrings](#docstrings)
- [Comments](#comments)
- [Errors and exceptions](#errors-and-exceptions)
- [Logging](#logging)
- [Public API and deprecations](#public-api-and-deprecations)
- [Tests](#tests)
- [Glossary](#glossary)

## Language

- **US English** everywhere: identifiers, comments, docstrings, log messages, docs (`serialize`, `behavior`, `color`, `canceled`).
- Use the words from the [glossary](#glossary) consistently. A "job" is never also a "task" or a "message".

## Formatting

- `ruff format` decides. Don't hand-format around it.
- Line length: **100**.
- Double quotes for strings; f-strings for interpolation.
- Imports: absolute (`from taskforge.worker.executor import execute_job`), sorted by Ruff into stdlib / third-party / first-party groups. No relative imports, no wildcard imports.
- One class or a small group of closely related functions per module; split a module when it passes about 400 lines. _(review)_
- Files end with a newline and use LF line endings (`.editorconfig` and `.gitattributes` take care of this).

## Naming

| Kind | Style | Example |
|---|---|---|
| Modules, packages | short, `lower_snake` | `worker`, `task_queue` |
| Functions, methods, variables | `lower_snake` | `enqueue_single_job`, `job_id` |
| Classes, exceptions | `PascalCase` | `Worker`, `AdminError` |
| Constants | `UPPER_SNAKE` | `HEARTBEAT_INTERVAL_SECONDS` |
| Private (not part of the API) | leading underscore | `_claim_next_job`, `_registry` |

- **Say what it is.** `job_id`, not `jid` or `id_`. Standard abbreviations are fine: `db`, `url`, `id`, `pid`.
- **Booleans read as yes/no questions:** `is_running`, `has_tags`, `enable_metrics`.
- **Units:** durations are seconds (as `int` or `float`). When the unit isn't obvious from the name, suffix it: `timeout_seconds`, `HEARTBEAT_INTERVAL_SECONDS`.
- **Functions are verbs** (`claim_job`), **values are nouns** (`queue_depth`).

## Type hints

- Every public function, method and attribute is fully annotated. Private helpers are annotated where it helps the reader. _(review)_
- Use modern syntax (Python 3.10+): `str | None`, `list[str]`, `dict[str, Any]`, and `collections.abc` for `Iterator`, `Callable`, `Mapping`.
- Prefer precise types to `Any`. When `Any` is right (arbitrary JSON, for example), name it with a type alias: `JSONValue = Any`.
- `# type: ignore` needs an error code and a reason: `# type: ignore[arg-type]  # SQLAlchemy stubs lag behind 2.0`.

## Docstrings

We use **Google style**. The docs site renders docstrings as Markdown (mkdocstrings), so use Markdown inside them: single backticks for code, and fenced blocks for examples.

### What needs one

| Item | Docstring |
|---|---|
| Public module (anything a user can import) | Required. A one-line summary; add a paragraph if the module isn't obvious. |
| Public class, function, method | Required, **full template** (below). |
| Public property or attribute | Required, as a noun phrase. |
| Private (`_name`) function or method | Only if the name and signature don't make it obvious. One line is usually enough. |
| Tests | Optional; the test name should say it all. Add one when the _why_ isn't obvious. |
| `__init__` | None. Document constructor arguments in the class docstring. |

### Writing rules

- **Summary line:** one line, imperative mood, ending with a period. "Claim the next runnable job.", not "Claims…" or "This function claims…".
- **Say what the caller needs:** behavior, guarantees, side effects (database writes, commits, threads started), and what happens on failure. Not how it's implemented.
- **Don't repeat type hints** in `Args`. Describe meaning, units, defaults and constraints instead.
- **Section order:** summary, description, `Args`, `Returns` (or `Yields`), `Raises`, `Example`, `Note` / `Warning`.
- **Omit empty sections.** A function returning `None` has no `Returns`.
- **Continuation lines** in a section are indented by 4 more spaces.
- **Mention the default** when it isn't in the signature (for example, when it comes from an environment variable).

### Templates

#### Module

```python
"""Worker process: claims jobs from the queue and executes them.

A worker polls one or more queues, claims one job at a time with
`SELECT ... FOR UPDATE SKIP LOCKED`, runs it, and records the outcome.
"""
```

#### Function / method

```python
def enqueue_single_job(
    job_type: str,
    payload: dict | list | None = None,
    queue_name: str = "default_queue",
    max_attempts: int | None = None,
) -> Job:
    """Add a job to a queue.

    The queue is created on first use. The job is committed before this
    function returns, so a worker can pick it up immediately.

    Args:
        job_type: Name the handler was registered under with `@register`.
        payload: Arguments for the handler. A dict is passed as keyword
            arguments and a list as positional arguments.
        queue_name: Queue to add the job to.
        max_attempts: Attempts before the job is moved to the dead-letter
            state, including the first run. Defaults to `DEFAULT_MAX_ATTEMPTS`.

    Returns:
        The persisted job, with its `id` set.

    Raises:
        sqlalchemy.exc.OperationalError: If the database is unreachable.

    Example:
        ```python
        enqueue_single_job("send_email", {"to": "ada@example.com"}, max_attempts=5)
        ```
    """
```

#### Class

```python
class Worker:
    """Poll queues and execute jobs, one at a time.

    Stop it with `stop()`, Ctrl+C or SIGTERM. The job in progress always
    finishes first.

    Args:
        queues: Queue names to consume from, in no particular order.
        poll_interval: Seconds to wait before polling again when no job is ready.

    Attributes:
        worker_id: Unique id of this worker, as stored in the `workers` table.
    """
```

#### Property

```python
@property
def is_running(self) -> bool:
    """Whether the worker's main loop is active."""
```

#### Exception class

```python
class AdminError(Exception):
    """An administrative action was rejected.

    Attributes:
        code: Machine-readable reason, e.g. `"not_found"` or `"already_replayed"`.
    """
```

#### Private helper (only when the name isn't enough)

```python
def _record_crash(self, job_id: str, error: str) -> None:
    """Count a failed attempt in a fresh session so the job doesn't stay `running`."""
```

## Comments

Comments explain **why**. The code already says **what**.

```python
# Bad: repeats the code
# Apply limit
stmt = stmt.limit(limit)

# Good: explains a decision the reader would otherwise question
# Reassign (don't mutate) the dict: SQLAlchemy doesn't track in-place JSON changes.
job.tags = {**tags, REPLAYED_AS_TAG: new_job.id}
```

Write a comment when:

- the code works around something (a library bug, a database quirk, a platform difference);
- there's a non-obvious ordering, locking or concurrency reason;
- a simpler-looking alternative was rejected ("why not just…?");
- a value is tuned ("15 s: short enough to detect lost workers within a minute").

Form:

- **Full sentences**, capitalized, ending with a period. Short inline fragments are fine: `x = 0  # reset per request`.
- **Inline comments** go two spaces after the code: `code  # comment`.
- **Section markers** in long modules: `# --- Job processing ---` (sentence case, three dashes on each side).
- **Links** to issues or external docs when they help: `# See #42` or `# https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE`.
- **TODOs must reference an issue:** `# TODO(#123): reclaim jobs from lost workers.` Never a bare `TODO`, and never names or dates (the issue has both).
- **Suppressions state a reason:** `# noqa: E402  (env must be set before TaskForge is imported)`.

Never, since this is a public repository: _(review)_

- commented-out code (git remembers it);
- secrets, tokens, internal hostnames or personal data, even in examples (use `example.com` and `user:password`);
- jokes at someone's expense, frustration ("this is stupid"), or blame;
- vague markers (`# hack`, `# XXX`, `# magic`) without an explanation;
- comments that go stale by design ("added in the Sept 2026 refactor").

## Errors and exceptions

- **Raise the most specific built-in** that fits (`ValueError`, `TypeError`, `LookupError`), or a TaskForge exception when callers need to catch it separately.
- **Messages:** sentence case, no trailing period. Include the offending value with `!r`, and say what to do when there's a fix: `f"Job type {job_type!r} is already registered to {existing}"`, or `"No database configured. Set TASKFORGE_DATABASE_URL (or DATABASE_URL)"`.
- **Never swallow exceptions silently.** If you catch broadly (`except Exception`), log it with `exc_info=True` and say why catching is safe here.
- **Chain** when re-raising: `raise AdminError(...) from exc`.

## Logging

- Every module uses `logger = logging.getLogger(__name__)`.
- **The library never configures logging.** No `basicConfig`, handlers or levels. Only entry points (the CLI, demo scripts) call `setup_logging()`.
- **Messages:** sentence case, no trailing period, past tense for events that happened ("Claimed job", "Worker registered").
- **Put data in `extra`,** so JSON logs are queryable. Use the standard keys: `job_id`, `job_type`, `queue`, `worker_id`, `attempt`. Add `event` (`PascalCase`, e.g. `JobReplayed`) for state changes a user might alert on.
- **Choose levels deliberately:**
  - `DEBUG`: internals;
  - `INFO`: lifecycle events;
  - `WARNING`: something went wrong, and TaskForge recovered or will retry;
  - `ERROR`: an operation failed;
  - `CRITICAL`: data may be stuck or lost.
- **Never log secrets or full payloads** at `INFO` or above; payloads can contain personal data.

## Public API and deprecations

- **Public** means importable without a leading underscore and documented. Everything else is private and may change without notice.
- Until 1.0, breaking changes are allowed but **must** appear in `CHANGELOG.md` under "Breaking".
- To remove or rename something public, keep a shim for at least one minor release that emits `DeprecationWarning` with the replacement:

  ```python
  warnings.warn(
      "enqueue_single_job() is deprecated; use TaskForge.enqueue() instead",
      DeprecationWarning,
      stacklevel=2,
  )
  ```

## Tests

- **Name tests after the behavior:** `test_<what>_<expected behavior>`, as in `test_stop_wakes_an_idle_worker_immediately`.
- **One behavior per test.** Arrange, act and assert, separated by a blank line (no `# Arrange` comments needed).
- **A bug fix comes with a test that fails without the fix.** Put it in the area's test file, or in `test_regressions.py` when the fix spans areas.
- **No sleeping for synchronization** when a condition can be polled with a deadline.

## Glossary

Use these terms and only these, in code and docs alike.

| Term | Meaning | Don't say |
|---|---|---|
| **job** | One unit of background work: a row in `jobs` | task, message |
| **job type** | The name a handler is registered under (`@register("send_email")`) | task name, job name |
| **handler** | The Python function that runs a job | task function, callback |
| **payload** | The arguments stored with a job | params, data |
| **queue** | A named stream of jobs | channel, topic |
| **worker** | A process (or `Worker` object) that claims and runs jobs | consumer, runner |
| **enqueue** | Add a job to a queue | push, publish, schedule (except for `scheduled_at`) |
| **claim** | A worker atomically taking a job to run it | lock, grab, pop |
| **attempt** | One execution of a job; `max_attempts` includes the first run | try, retry (for the first run) |
| **retry** | Any attempt after the first | |
| **dead** / **dead-letter** | Out of attempts; waits for manual action | failed (that's the "waiting for retry" state), DLQ in prose |
| **replay** | Re-enqueue a dead job as a new job | retry, requeue |
