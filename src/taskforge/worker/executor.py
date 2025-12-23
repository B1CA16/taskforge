import traceback
from typing import Any, Dict, Tuple
from taskforge.jobs.registry import get_job_func
from taskforge.task_queue.models import Job


def execute_job(job: Job) -> Tuple[Any, str | None]:
    """
    Executes a job and returns the result and any error message.
    """
    try:
        job_func = get_job_func(job.type)

        # The payload can be None, a list (for positional args), or a dict (for keyword args)
        payload = job.payload or {}

        if isinstance(payload, list):
            result = job_func(*payload)
        elif isinstance(payload, dict):
            result = job_func(**payload)
        else:
            raise TypeError(f"Unsupported payload type: {type(payload)}")

        return result, None
    except Exception:
        error_message = traceback.format_exc()
        return None, error_message
