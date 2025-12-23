import os

# The default number of times a job will be retried before being moved to the dead-letter queue.
# This can be overridden by setting the DEFAULT_MAX_ATTEMPTS environment variable.
DEFAULT_MAX_ATTEMPTS: int = int(os.getenv("DEFAULT_MAX_ATTEMPTS", "3"))
