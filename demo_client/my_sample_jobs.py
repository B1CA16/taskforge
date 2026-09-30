import logging
import time

from taskforge.jobs.registry import register


@register("greet_user")
def greet_user(name: str, logger: logging.Logger | None = None):
    """A sample job that prints a greeting and simulates work."""
    if logger:
        logger.info(f"Hello, {name}! This is a registered job speaking.")
    else:
        print(f"Hello, {name}! This is a registered job speaking.")
    time.sleep(2)  # Simulate some work
    return f"Greeting job completed for {name}."


@register("add_numbers")
def add_numbers(a: int, b: int, logger: logging.Logger | None = None):
    """A sample job that adds two numbers."""
    result = a + b
    if logger:
        logger.info(f"Adding {a} and {b}. Result: {result}")
    else:
        print(f"Adding {a} and {b}. Result: {result}")
    return result


@register("fail_example")
def fail_example(message: str, logger: logging.Logger | None = None):
    """A sample job that is designed to fail."""
    if logger:
        logger.error(f"This job is designed to fail: {message}")
    else:
        print(f"This job is designed to fail: {message}")
    raise ValueError(f"Job failed: {message}")
