"""TaskForge: background jobs for Python, stored in your Postgres database."""

import logging
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("taskforge-queue")
except PackageNotFoundError:  # running from a source checkout without installing
    __version__ = "0.0.0+unknown"

# Library best practice: emit records, never configure handlers for the host app.
logging.getLogger(__name__).addHandler(logging.NullHandler())
