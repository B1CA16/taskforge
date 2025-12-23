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

-   Jobs track `attempts` and `max_attempts`
-   Failed jobs can be retried automatically
-   Backoff strategy: exponential by default
-   Jobs exceeding max attempts go to dead letter queue

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
| `max_attempts`  | integer   | Maximum retry limit                                            |
| `locked_by`     | string    | Worker that claimed the job                                    |
| `locked_at`     | timestamp | Time when job was claimed                                      |
| `result`        | JSON      | Output of the job                                              |
| `error_message` | text      | Last error message                                             |

### Queue Model

| Field  | Type   | Description                                                  |
| ------ | ------ | ------------------------------------------------------------ |
| `id`   | UUID   | Unique identifier                                            |
| `name` | string | Unique name for the queue (e.g., `high_priority`, `default`) |

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
