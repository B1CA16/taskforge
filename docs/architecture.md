# Architecture Overview

## Core Concepts

-   **Job**: A unit of work to be executed in the background.
-   **Queue**: A named container for jobs. Each job belongs to a single queue.
-   **Worker**: A process that polls for jobs from a queue, executes them, and updates their status.

## Job Lifecycle

-   `pending` → `running` → `done`
-   `running` → `failed` (attempt failed, retry scheduled) → `running` → …
-   `running` → `dead` once `max_attempts` is reached (the dead-letter state)
-   All timestamps are stored as timezone-aware UTC (`timestamptz` on Postgres)

### Locking & Concurrency

-   Each job has `locked_by` and `locked_at` fields
-   Workers claim jobs using atomic database operations:
    -   PostgreSQL: `SELECT ... FOR UPDATE SKIP LOCKED`
-   Workers register in the `workers` table and send a heartbeat every 15 s. A worker
    whose heartbeat is older than 60 s is shown as `lost` in the CLI and dashboard.
-   **Not implemented yet:** reclaiming jobs from a lost worker. If a worker process is
    killed mid-job, the job stays `running` until it's handled manually. A graceful stop
    (Ctrl+C, SIGTERM, Ctrl+Break) always lets the current job finish first.

### Retries & Backoff

To handle transient failures, the system has a built-in automatic retry mechanism.

-   **Process**: When a job fails, the `Worker` checks if `job.attempts < job.max_attempts`.
-   **Retry**: If the job can be retried, the `Worker`:
    1.  Increments `job.attempts`.
    2.  Sets the status to `failed` (a worker picks it up again once `scheduled_at` has passed).
    3.  Calculates a new `scheduled_at` timestamp using an exponential backoff formula (`10 * (2 ** attempts)` seconds), preventing failing jobs from overwhelming the system.
-   **Dead-Letter Queue**: If a job fails and has no retries left, its status is changed to `dead`. This effectively removes it from normal processing and places it in a "dead-letter" state, allowing for manual inspection later.

## Model Definitions

### Job Model

| Field           | Type      | Description                                                          |
| --------------- | --------- | -------------------------------------------------------------------- |
| `id`            | UUID      | Unique identifier                                                    |
| `queue_id`      | UUID      | Foreign key to the `queues` table                                    |
| `type`          | string    | Job type / function to execute                                       |
| `payload`       | JSON      | Data required for execution                                          |
| `status`        | enum      | Current state (`pending`, `running`, `done`, `failed`, `dead`)       |
| `created_at`    | timestamptz | When job was created                                                 |
| `updated_at`    | timestamptz | Last status update                                                   |
| `scheduled_at`  | timestamptz | When job is scheduled to run                                         |
| `attempts`      | integer   | Number of attempts                                                   |
| `max_attempts`  | integer   | Maximum retry limit (configured globally, can be overridden per-job) |
| `locked_by`     | string    | Worker that claimed the job                                          |
| `locked_at`     | timestamptz | Time when job was claimed                                            |
| `result`        | JSON      | Output of the job                                                    |
| `error_message` | text      | Last error message                                                   |

### Queue Model

| Field  | Type   | Description                                                  |
| ------ | ------ | ------------------------------------------------------------ |
| `id`   | UUID   | Unique identifier                                            |
| `name` | string | Unique name for the queue (e.g., `high_priority`, `default`) |

## Configuration

Core system settings are managed through environment variables, typically loaded from a `.env` file at the root of the project. These settings are accessed via `src/taskforge/config/settings.py`.

-   **`DEFAULT_MAX_ATTEMPTS`**: Defines the default maximum number of times a job will be attempted (including the initial run) before being moved to the `dead` state.
    -   **Global Configuration**: Set this environment variable in your `.env` file to apply a project-wide default (e.g., `DEFAULT_MAX_ATTEMPTS=5`).
    -   **Per-Job Override**: This global default can be overridden for individual jobs by explicitly setting the `max_attempts` parameter when enqueuing a job.

## Worker Design

The worker implementation is divided into three distinct components to ensure a clear separation of concerns.

1.  **Job Registry (`jobs/registry.py`)**: Acts as a central mapping from a job's `type` (a string) to the actual Python function that should be executed. This is achieved via a simple `register` decorator.

2.  **Executor (`worker/executor.py`)**: This component is responsible for the actual execution of a job's code. It fetches the appropriate function from the registry, calls it with the job's payload, and captures any return value or exceptions.

3.  **Worker (`worker/worker.py`)**: This is the core component that runs the main polling loop. It is responsible for the entire lifecycle of a job, excluding its execution.
    -   It polls the database periodically for pending jobs.
    -   It uses a single, atomic `UPDATE ... RETURNING` query with `FOR UPDATE SKIP LOCKED` to find, lock, and update a job's status to `running` in one database round-trip.
    -   It passes the locked job to the Executor.
    -   Based on the outcome from the Executor, it updates the job's status to `done` or `failed` and records the result or error message.
    -   All its operations leverage the **Structured Logging** system for clear, machine-readable output.

This design decouples the lifecycle management of a job (the Worker) from its business logic (the Executor and registered functions).

## Observability

To provide insight into the system's runtime behavior and state, TaskForge incorporates structured logging and a command-line inspection tool.

### Structured Logging

-   **Mechanism**: All application and worker logs are generated using Python's standard `logging` module, configured centrally via `src/taskforge/config/logging.py`.
-   **Format**: Logs are emitted in **JSON format**, making them easy to parse, filter, and analyze with external tools (e.g., ELK stack, Splunk, cloud logging services).
-   **Contextual Information**: The `Worker` uses `logging.LoggerAdapter` to automatically inject context such as `job_id`, `worker_id`, and `job_type` into every log message related to a specific job. This ensures that every event can be easily traced back to its origin.
-   **SQLAlchemy Integration**: SQLAlchemy's internal engine logs are captured and routed through this same structured logging system, with its verbosity reduced to `WARNING` level by default to prevent excessive output, while still allowing critical database events to be seen.
-   **Best Practice for Jobs**: User-defined job functions should accept an optional `logger` argument and use `logger.info()`, `logger.warning()`, etc., instead of `print()`, to integrate their messages into the structured log stream.

### CLI Inspection Tools

A basic command-line interface (CLI) is provided to inspect the state of the job queue directly from the terminal.

-   **Location**: `src/taskforge/cli/main.py`
-   **Usage**: The CLI tool also utilizes the structured logging system for its output.
-   **`dead-letter` command**:
    -   **Purpose**: Lists all jobs that are currently in the `dead` state, providing details such as job ID, type, attempts, failure timestamp, and the last error message. This is crucial for reviewing jobs that have exhausted all retry attempts and require manual intervention.
    -   **How to run**: `python -m taskforge.cli.main dead-letter`

## Guidelines & Rules

-   Write tests for core functionality
-   Document any new design decisions in `docs/architecture.md`
-   Keep jobs idempotent to ensure at-least-once execution

## Guarantees

-   At-least-once execution
-   Jobs may be retried, so payloads should handle multiple runs

## Non-goals

-   Exactly-once execution
-   Real-time guarantees
