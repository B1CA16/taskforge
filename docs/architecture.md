# Architecture Overview

## Core Concepts

-   **Job**: A unit of work to be executed in the background.
-   **Queue**: A named container for jobs. Each job belongs to a single queue.
-   **Worker**: A process that polls for jobs from a queue, executes them, and updates their status.

## Job Lifecycle

-   `pending` → `running` → `done` / `failed`
-   Optional `dead` state for jobs that exceed retry limits

### Locking & Concurrency

-   Each job has `locked_by` and `locked_at` fields
-   Workers claim jobs using atomic database operations:
    -   PostgreSQL: `SELECT ... FOR UPDATE SKIP LOCKED`
-   If a worker dies while processing, jobs can be reclaimed after a lock timeout

### Retries & Backoff

To handle transient failures, the system has a built-in automatic retry mechanism.

-   **Process**: When a job fails, the `Worker` checks if `job.attempts < job.max_attempts`.
-   **Retry**: If the job can be retried, the `Worker`:
    1.  Increments `job.attempts`.
    2.  Resets the status to `pending`.
    3.  Calculates a new `scheduled_at` timestamp using an exponential backoff formula (`10 * (2 ** attempts)` seconds), preventing failing jobs from overwhelming the system.
-   **Dead-Letter Queue**: If a job fails and has no retries left, its status is changed to `dead`. This effectively removes it from normal processing and places it in a "dead-letter" state, allowing for manual inspection later.

## Model Definitions

### Job Model

| Field           | Type      | Description                                                    |
| --------------- | --------- | -------------------------------------------------------------- |
| `id`            | UUID      | Unique identifier                                              |
| `queue_id`      | UUID      | Foreign key to the `queues` table                              |
| `type`          | string    | Job type / function to execute                                 |
| `payload`       | JSON      | Data required for execution                                    |
| `status`        | enum      | Current state (`pending`, `running`, `done`, `failed`, `dead`) |
| `created_at`    | timestamp | When job was created                                           |
| `updated_at`    | timestamp | Last status update                                             |
| `scheduled_at`  | timestamp | When job is scheduled to run                                   |
| `attempts`      | integer   | Number of attempts                                             |
| `max_attempts`  | integer   | Maximum retry limit (configured globally, can be overridden per-job) |
| `locked_by`     | string    | Worker that claimed the job                                    |
| `locked_at`     | timestamp | Time when job was claimed                                      |
| `result`        | JSON      | Output of the job                                              |
| `error_message` | text      | Last error message                                             |

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

This design decouples the lifecycle management of a job (the Worker) from its business logic (the Executor and registered functions).

## Guidelines & Rules

-   Write tests for core functionality
-   Document any new design decisions in `ARCHITECTURE.md`
-   Keep jobs idempotent to ensure at-least-once execution

## Guarantees

-   At-least-once execution
-   Jobs may be retried, so payloads should handle multiple runs

## Non-goals

-   Exactly-once execution
-   Real-time guarantees
