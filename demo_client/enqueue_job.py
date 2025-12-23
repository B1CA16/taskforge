import sys
import os

# Adjust sys.path to include the project's 'src' directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))


from taskforge.db.connection import get_session
from taskforge.task_queue.models import Job, Queue, JobStatus
from taskforge.jobs.registry import register # Ensure registry is loaded

# Import your sample jobs file to register the job functions
import my_sample_jobs # This import runs the @register decorators

def enqueue_single_job(job_type: str, payload: dict | list | None = None, queue_name: str = "default_queue"):
    """Enqueues a single job into the specified queue."""
    with get_session() as session:
        # Ensure the queue exists, create if not
        queue = session.query(Queue).filter_by(name=queue_name).first()
        if not queue:
            print(f"Queue '{queue_name}' not found, creating it.")
            queue = Queue(name=queue_name)
            session.add(queue)
            session.commit()
            session.refresh(queue)

        # Create and add the job
        job = Job(type=job_type, payload=payload, queue_id=queue.id, status=JobStatus.pending)
        session.add(job)
        session.commit()
        session.refresh(job)
        print(f"Enqueued job {job.id} (type: '{job.type}') to queue '{queue_name}'. Initial Status: {job.status}")
        return job

if __name__ == "__main__":
    print("--- Enqueueing Jobs ---")
    enqueue_single_job("greet_user", {"name": "Alice"})
    enqueue_single_job("add_numbers", {"a": 10, "b": 20}) # Using dict for kwargs
    enqueue_single_job("greet_user", {"name": "Bob"})
    enqueue_single_job("add_numbers", [5, 7]) # Using list for args
    enqueue_single_job("fail_example", {"message": "Something critical failed!"})
    print("--- Jobs Enqueued ---")
