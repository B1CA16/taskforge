"""Global settings read from environment variables."""

import os

DEFAULT_MAX_ATTEMPTS: int = int(os.getenv("DEFAULT_MAX_ATTEMPTS", "3"))
"""Attempts per job, including the first run, before it moves to `dead`.

Set with the `DEFAULT_MAX_ATTEMPTS` environment variable; override per job with
`max_attempts` when enqueueing.
"""
