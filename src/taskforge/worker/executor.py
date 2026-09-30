import inspect
import logging
import traceback
from typing import Any, Optional, Tuple

from taskforge.jobs.registry import get_job_func
from taskforge.task_queue.models import Job

logger = logging.getLogger(__name__)


def execute_job(
    job: Job, logger: Optional[logging.Logger] = None
) -> Tuple[Any, str | None]:
    """Run the function registered for ``job.type`` with the job's payload.

    A ``dict`` payload is passed as keyword arguments and a ``list`` as
    positional arguments. If the function declares a ``logger`` parameter, the
    job-scoped logger is injected.

    Returns:
        ``(result, None)`` on success, or ``(None, traceback_text)`` if the job
        raised. Exceptions never propagate to the caller.
    """
    try:
        job_func = get_job_func(job.type)
        payload = job.payload or {}
        sig = inspect.signature(job_func)

        kwargs: dict[str, Any] = {}
        args: list[Any] = []

        # Copy the payload: it is the ORM attribute, and mutating it (e.g. by
        # injecting the logger below) would leak into the persisted job row.
        if isinstance(payload, dict):
            kwargs = dict(payload)
        elif isinstance(payload, list):
            args = list(payload)
        else:
            raise TypeError(f"Unsupported payload type: {type(payload)}")

        if "logger" in sig.parameters:
            kwargs["logger"] = logger

        result = job_func(*args, **kwargs)

        return result, None
    except Exception:
        error_message = traceback.format_exc()
        if logger:
            logger.error(f"Job {job.id} execution failed.", exc_info=True)
        return None, error_message
