import os
import sys

# Adjust sys.path to include the project's 'src' directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))


from taskforge.config.logging import setup_logging
from taskforge.task_queue.db import enqueue_single_job

if __name__ == "__main__":
    setup_logging()
    print("--- Enqueueing Jobs ---")
    enqueue_single_job("greet_user", {"name": "Alice"}, tags={"env": "demo", "team": "onboarding"})
    enqueue_single_job("add_numbers", {"a": 10, "b": 20}, tags={"env": "demo"})
    enqueue_single_job(
        "fail_example",
        {"message": "This will be retried"},
        max_attempts=5,
        tags={"env": "demo", "priority": "low"},
    )
    enqueue_single_job("add_numbers", [5, 7], tags={"env": "demo"})
    enqueue_single_job(
        "fail_example",
        {"message": "This will only try once"},
        max_attempts=1,
        tags={"env": "demo", "priority": "high"},
    )
    print("--- Jobs Enqueued ---")
