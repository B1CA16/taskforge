# TaskForge Testing Strategy

This document outlines the testing strategy for the TaskForge project. It covers the current state of testing, identifies gaps, and proposes new tests to improve code quality and reliability.

## Current Test Coverage

The project has a good foundation of unit and integration tests covering several key areas:

- **Worker Lifecycle (`test_worker.py`):**
  - **Success:** A worker can claim, execute, and mark a job as `done`.
  - **Retry:** A failed job is correctly rescheduled with an exponential backoff.
  - **Failure:** A job that exhausts its retries is moved to the `dead` state.
- **Job Registry (`test_worker.py`):**
  - The `@register` decorator correctly maps a job type to a function.
  - The system raises an error when trying to execute an unregistered job.
- **Job Execution (`test_worker.py`):**
  - Payloads are correctly passed to the job functions.
  - The executor can inject a `logger` into the job function.
  - Exceptions during job execution are caught and recorded.
- **Configuration (`test_config.py`):**
  - Default settings are applied correctly.
  - Per-job settings override global defaults.
  - Settings can be configured via environment variables.
- **CLI (`test_cli.py`):**
  - The `dead-letter` command correctly displays failed jobs and handles the empty case.

## Identified Gaps and Areas for Improvement

While the current tests are valuable, several critical areas remain under-tested.

### 1. Database and Model Integrity

The existing `test_queue_session.py` is insufficient and lacks assertions.

- **Missing Tests:**
  - **Uniqueness Constraints:** Test that creating a `Queue` with a duplicate name raises an `IntegrityError`.
  - **Foreign Keys:** Test that creating a `Job` without a valid `queue_id` fails.
  - **Model Relationships:** Explicitly test the `queue.jobs` and `job.queue` relationships.

### 2. Worker Concurrency

The most significant gap is the lack of concurrency testing. The `FOR UPDATE SKIP LOCKED` mechanism is designed to prevent race conditions, but this is not verified by any test.

- **Missing Tests:**
  - **Race Conditions:** Simulate multiple workers (in separate threads or processes) trying to claim jobs from the same queue simultaneously. The test should verify that each job is processed only once.

### 3. Executor and Job Edge Cases

The executor logic needs to be hardened against invalid inputs.

- **Missing Tests:**
  - **Payload Mismatch:** Test the executor's behavior when a job's payload doesn't match the signature of the registered function (e.g., wrong argument names in a `dict`, or wrong number of elements in a `list`). This should result in a graceful failure, not an unhandled exception.
  - **Unsupported Payload Type:** Test the `TypeError` that should be raised for payloads that are not a `list` or `dict`.

### 4. Scheduled Jobs

The worker has logic to ignore jobs scheduled for the future (`scheduled_at > NOW()`), but this is not tested.

- **Missing Tests:**
  - **Future Jobs:** Create a job with a `scheduled_at` in the future. Run a worker and assert that the job is *not* picked up.
  - **Past-Due Jobs:** Create a job with a `scheduled_at` in the past. Run a worker and assert that the job *is* picked up.

## Proposed Plan for New Tests

To address these gaps, the following tests will be implemented:

1.  **Refactor `test_queue_session.py`:**
    - Rename it to `test_db_models.py` for clarity.
    - Add tests for uniqueness, foreign key constraints, and model relationships.

2.  **Create `test_concurrency.py`:**
    - Implement a test that spawns multiple `Worker` instances in threads.
    - Have them all poll a queue with multiple jobs.
    - Use a shared, thread-safe counter or list to track how many times each job is executed.
    - Assert that each job was processed exactly once.

3.  **Expand `test_worker.py` (Executor section):**
    - Add tests for mismatched `dict` and `list` payloads.
    - Add a test to confirm the `TypeError` for invalid payload types.

4.  **Expand `test_worker.py` (Worker section):**
    - Add tests to verify the `scheduled_at` logic for future- and past-dated jobs.
