from typing import Callable, Dict

_job_registry: Dict[str, Callable] = {}


def register(job_type: str) -> Callable:
    """Register the decorated function as the handler for ``job_type``.

    Registering the same function twice is a no-op (modules can be re-imported),
    but registering a *different* function under a name that is already taken
    raises, since silently replacing a handler is almost always a bug.

    Raises:
        ValueError: If ``job_type`` is already registered to another function.
    """

    def decorator(func: Callable) -> Callable:
        existing = _job_registry.get(job_type)
        if existing is not None and existing is not func and not _same_function(existing, func):
            raise ValueError(
                f"Job type {job_type!r} is already registered to "
                f"{existing.__module__}.{existing.__qualname__}"
            )
        _job_registry[job_type] = func
        return func

    return decorator


def _same_function(a: Callable, b: Callable) -> bool:
    # The same function re-created by a module reload is a different object.
    return (
        getattr(a, "__module__", None) == getattr(b, "__module__", None)
        and getattr(a, "__qualname__", None) == getattr(b, "__qualname__", None)
    )


def get_job_func(job_type: str) -> Callable:
    """Return the function registered for ``job_type``.

    Raises:
        ValueError: If no function is registered under that name.
    """
    if job_type not in _job_registry:
        raise ValueError(f"No job function registered for type: {job_type}")
    return _job_registry[job_type]
