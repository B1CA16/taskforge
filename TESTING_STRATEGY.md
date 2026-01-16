# TaskForge Testing Strategy

This document outlines the testing strategy and coverage for the TaskForge project. The test suite is designed to ensure the reliability, correctness, and robustness of the library.

## Testing Philosophy

Tests are a cornerstone of this project and are organized to cover functionality at different levels:

-   **Unit Tests:** For individual functions and isolated logic (e.g., job registration).
-   **Integration Tests:** For components that work together (e.g., the worker processing a job from the database).
-   **Edge Case Tests:** To ensure the system behaves gracefully with unexpected inputs or in specific scenarios.

The test suite uses `pytest` and an in-memory SQLite database for speed and isolation, allowing tests to run without external dependencies.

## Comprehensive Test Coverage

The test suite provides extensive coverage across all major features of the library.

### 1. Worker and Job Lifecycle

-   **Successful Execution:** A worker correctly claims, executes, and marks a job as `done`.
-   **Automatic Retries:** A failed job is automatically retried with an exponential backoff delay, and its `attempts` count is incremented.
-   **Dead-Letter Queue:** A job that exhausts all its retry attempts is correctly moved to the `dead` status.

### 2. Concurrency
-   **Race Condition Prevention:** A dedicated multi-threaded test (`test_concurrency.py`) simulates multiple workers polling the same queue. It verifies that the `FOR UPDATE SKIP LOCKED` mechanism correctly prevents race conditions, ensuring each job is processed **exactly once**.

### 3. Job Scheduling
-   **Future-Dated Jobs:** The worker correctly ignores jobs whose `scheduled_at` time is in the future.
-   **Past-Due Jobs:** The worker correctly picks up jobs whose `scheduled_at` time has passed.

### 4. Job Definition and Execution
-   **Job Registry:** The `@register` decorator works as expected, and the system correctly handles requests for unregistered jobs.
-   **Executor Logic:** The executor correctly passes `dict` and `list` payloads to job functions.
-   **Logger Injection:** A job-specific logger is successfully injected into job functions that request it.
-   **Exception Handling:**
    -   Exceptions raised within a job function are caught, and the error is logged.
    -   The executor gracefully handles `TypeError` exceptions that arise from mismatched job payloads (e.g., wrong number of arguments).
    -   The executor correctly fails jobs with unsupported payload types (e.g., a raw string).

### 5. Database and Model Integrity
-   **Uniqueness Constraints:** The database correctly enforces that queue names must be unique.
-   **Foreign Key Constraints:** The database correctly prevents the creation of a `Job` with a `queue_id` that does not exist.
-   **Model Relationships:** The SQLAlchemy relationships between `Job` and `Queue` are verified.

### 6. Configuration
-   **Default Settings:** Global settings like `DEFAULT_MAX_ATTEMPTS` are applied correctly.
-   **Per-Job Overrides:** Job-specific settings (e.g., `max_attempts`) correctly override global defaults.
-   **Environment Variables:** Configuration via environment variables is tested and works as expected.

### 7. Command-Line Interface (CLI)
-   The `dead-letter` command correctly fetches and displays jobs from the dead-letter queue.
-   The command handles the case where the dead-letter queue is empty.