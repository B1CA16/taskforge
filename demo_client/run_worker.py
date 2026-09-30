import sys
import os

# Adjust sys.path to include the project's 'src' directory
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

from taskforge.config.logging import setup_logging
from taskforge.worker.worker import Worker

# Import your sample jobs file to register the job functions
import my_sample_jobs  # This import runs the @register decorators

if __name__ == "__main__":
    setup_logging()
    print("--- Starting Worker (Ctrl+C to stop after the current job) ---")
    worker = Worker(queues=["default_queue"])
    try:
        worker.run()
    except KeyboardInterrupt:
        print("--- Worker aborted ---")
    else:
        print("--- Worker stopped ---")
