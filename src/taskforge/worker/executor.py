import inspect
import logging
import traceback
from typing import Any, Tuple, Callable, Optional
from taskforge.jobs.registry import get_job_func
from taskforge.task_queue.models import Job
from taskforge.config.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def execute_job(
    job: Job, logger: Optional[logging.Logger] = None
) -> Tuple[Any, str | None]:
    """
    Executes a job and returns the result and any error message.
    """
    try:
        job_func = get_job_func(job.type)
        payload = job.payload or {}
        sig = inspect.signature(job_func)

        kwargs = {}
        args = []

        if isinstance(payload, dict):
            kwargs = payload
        elif isinstance(payload, list):
            args = payload
        else:
            raise TypeError(f"Unsupported payload type: {type(payload)}")

        # If the function accepts a 'logger' keyword argument, pass it in
        if "logger" in sig.parameters:
            kwargs["logger"] = logger

        result = job_func(*args, **kwargs)

        return result, None
    except Exception:
        error_message = traceback.format_exc()
        if logger:
            logger.error(f"Job {job.id} execution failed.", exc_info=True)
        return None, error_message
