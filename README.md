# TaskForge

**TaskForge** is a lightweight, durable, and reliable background job processing library for Python, built with a database-backed queueing system.

It enables you to define, enqueue, and execute tasks asynchronously, outside of the request/response cycle of a typical web application. It is designed for simplicity, reliability, and easy integration into any Python project.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What is TaskForge?

In many applications, there are tasks that you don't want to run during the user's web request because they are too slow (e.g., sending an email, processing an image, generating a report). TaskForge provides the infrastructure to offload these tasks to a background "worker" process.

A central component, the **queue**, stores jobs in your database. A **worker** process polls the queue for new jobs, executes them, and records the outcome.

## Key Features

- **Database-Backed Queue:** Uses your existing database (via SQLAlchemy) to provide durable, persistent job storage. If the worker restarts, your jobs are not lost.
- **Decorator-Based Job Creation:** Define your background jobs with a simple `@register` decorator on your Python functions.
- **Automatic Retries with Exponential Backoff:** If a job fails, TaskForge will automatically retry it several times with an increasing delay, which helps recover from transient errors.
- **Dead-Letter Queue:** After a job has failed all its retry attempts, it is moved to a "dead-letter" queue so it can be inspected and handled manually.
- **Concurrency-Safe Workers:** You can run multiple worker processes simultaneously to scale up your job processing throughput. A robust locking mechanism (`SELECT ... FOR UPDATE SKIP LOCKED`) ensures that each job is processed by only one worker.
- **Scheduled Jobs:** Enqueue jobs to run at a specific time in the future.
- **Command-Line Interface (CLI):** Includes a handy CLI for administrative tasks, such as viewing the dead-letter queue.

## Installation

_(This project is not yet packaged for PyPI. The following are instructions for local development.)_

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/taskforge.git
    cd taskforge
    ```

2.  **Install dependencies:**
    It is recommended to use a virtual environment.
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
    pip install -r requirements.txt 
    ```
    _(Note: A `requirements.txt` would need to be created for this step)_

## Getting Started: A Quick Example

The `demo_client` directory contains a simple example to showcase how TaskForge works.

### 1. Define Your Jobs

Create a file for your job functions and decorate them with `@register`.

`demo_client/my_sample_jobs.py`:
```python
from taskforge.jobs.registry import register
import time
import logging

@register("greet_user")
def greet_user(name: str, logger: logging.Logger):
    """A sample job that prints a greeting."""
    logger.info(f"Hello, {name}! This is a registered job speaking.")
    time.sleep(2)
    return f"Greeting job completed for {name}."

@register("fail_example")
def fail_example(message: str, logger: logging.Logger):
    """A sample job that is designed to fail."""
    logger.error(f"This job is designed to fail: {message}")
    raise ValueError(f"Job failed: {message}")
```

### 2. Enqueue Jobs

From your application code, you can enqueue a job to be run in the background.

`demo_client/enqueue_job.py`:
```python
from taskforge.task_queue.db import enqueue_single_job
import my_sample_jobs # Ensures jobs are registered

print("--- Enqueueing Jobs ---")
# Enqueue a job to the 'default_queue'
enqueue_single_job("greet_user", {"name": "Alice"})

# Enqueue a job that will fail and be retried
enqueue_single_job(
    "fail_example", 
    {"message": "This will be retried"}, 
    max_attempts=5
)
print("--- Jobs Enqueued ---")
```

### 3. Run the Worker

Start a worker process in a separate terminal. The worker will poll the queue and execute any jobs it finds.

```bash
# In Terminal 1
python demo_client/run_worker.py
```
You will see logs indicating the worker has started and is polling the queue.

### 4. Run the Enqueuer

In another terminal, run the script to add the jobs to the queue.

```bash
# In Terminal 2
python demo_client/enqueue_job.py
```

You will now see log output in Terminal 1 as the worker picks up, executes, and completes (or fails) the jobs.

## Usage

### Defining Jobs

- Any function can be turned into a background job by adding the `@register("job_type_name")` decorator.
- The `job_type_name` is a unique string that identifies the job.
- The function can accept arguments. These will be passed in the `payload` when the job is enqueued.
- For best practice, include a `logger` argument in your function signature. TaskForge will automatically inject a job-specific logger.

### Enqueuing Jobs

The `taskforge.task_queue.db.enqueue_single_job` function is the primary way to create new jobs.

```python
enqueue_single_job(
    job_type: str,
    payload: dict | list | None = None,
    queue_name: str = "default_queue",
    max_attempts: int | None = None,
    scheduled_at: datetime | None = None
)
```

- `job_type`: The string name you used in the `@register` decorator.
- `payload`: A `dict` (for keyword arguments) or `list` (for positional arguments) to pass to your job function.
- `queue_name`: The name of the queue to add the job to.
- `max_attempts`: Override the default number of retries for this specific job.
- `scheduled_at`: A `datetime` object specifying when the job should be executed.

## Configuration



-   **Database Connection:** TaskForge uses SQLAlchemy to connect to the database. The connection string *must* be provided via the `DATABASE_URL` environment variable (e.g., in a `.env` file or directly in your environment). TaskForge expects this variable to be set.

    Example: `DATABASE_URL="postgresql://user:password@host:port/database_name"`

-   **Default Max Attempts:** The global default for job retries can be set with the `DEFAULT_MAX_ATTEMPTS` environment variable. The default is `3`.

## Command-Line Interface

TaskForge provides a CLI for administrative tasks.

### View Dead-Letter Queue

To see jobs that have failed all their retry attempts, use the `dead-letter` command:

```bash
python -m taskforge.cli.main dead-letter
```

This will print a list of all jobs in the `dead` status, along with their last error message, for easier debugging.

## Running Tests

The project includes a comprehensive test suite.

1.  **Install testing dependencies:**
    ```bash
    pip install pytest
    ```

2.  **Run the tests:**
    ```bash
    pytest
    ```

See the `TESTING_STRATEGY.md` file for a detailed overview of the testing approach.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.