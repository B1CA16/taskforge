import sys
import os
import time

# Adjust sys.path to include the project's 'src' directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from taskforge.worker.worker import Worker
from taskforge.jobs.registry import register # Ensure registry is loaded

# Import your sample jobs file to register the job functions
import my_sample_jobs # This import runs the @register decorators

if __name__ == "__main__":
    print("--- Starting Worker ---")
    worker = Worker(queues=["default_queue"])
    try:
        # Run continuously. Use Ctrl+C to stop.
        worker.run()
    except KeyboardInterrupt:
        worker.stop()
        print("--- Worker stopped by user ---")
    except Exception as e:
        print(f"--- Worker crashed: {e} ---")