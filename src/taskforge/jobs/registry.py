from typing import Callable, Dict

_job_registry: Dict[str, Callable] = {}


def register(job_type: str) -> Callable:
    """
    Decorator to register a function as a job handler.
    """
    def decorator(func: Callable) -> Callable:
        _job_registry[job_type] = func
        return func
    return decorator


def get_job_func(job_type: str) -> Callable:
    """
    Retrieves the function associated with a given job type.
    """
    if job_type not in _job_registry:
        raise ValueError(f"No job function registered for type: {job_type}")
    return _job_registry[job_type]
