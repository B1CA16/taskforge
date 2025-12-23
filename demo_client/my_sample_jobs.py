from taskforge.jobs.registry import register
import time


@register("greet_user")
def greet_user(name: str):
    """A sample job that prints a greeting and simulates work."""
    print(f"Hello, {name}! This is a registered job speaking.")
    time.sleep(2)  # Simulate some work
    return f"Greeting job completed for {name}."


@register("add_numbers")
def add_numbers(a: int, b: int):
    """A sample job that adds two numbers."""
    result = a + b
    print(f"Adding {a} and {b}. Result: {result}")
    return result


@register("fail_example")
def fail_example(message: str):
    """A sample job that is designed to fail."""
    print(f"This job is designed to fail: {message}")
    raise ValueError(f"Job failed: {message}")
