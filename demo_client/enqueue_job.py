import sys
import os

# Adjust sys.path to include the project's 'src' directory
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

from taskforge.task_queue.db import enqueue_single_job
import my_sample_jobs  # This import runs the @register decorators


if __name__ == "__main__":
    print("--- Enqueueing Jobs ---")
    enqueue_single_job("greet_user", {"name": "Alice"})
    enqueue_single_job("add_numbers", {"a": 10, "b": 20})
    enqueue_single_job(
        "fail_example", {"message": "This will be retried"}, max_attempts=5
    )  # Override default
    enqueue_single_job("add_numbers", [5, 7])
    enqueue_single_job(
        "fail_example", {"message": "This will only try once"}, max_attempts=1
    )  # Override default
    print("--- Jobs Enqueued ---")

