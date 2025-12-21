# Architecture Overview

## Core Concepts

-   Job
-   Queue
-   Worker

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

## Job Model Fields

| Field           | Type      | Description                                                    |
| --------------- | --------- | -------------------------------------------------------------- |
| `id`            | UUID      | Unique identifier                                              |
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

## Worker Responsibilities

-   Poll jobs from the queue
-   Claim jobs atomically
-   Execute job payload
-   Update job status
-   Handle retries, backoff, and errors

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
