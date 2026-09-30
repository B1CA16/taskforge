"""Log formatters and `setup_logging()` for TaskForge's own entry points."""

import json
import logging
import sys
from datetime import datetime, timezone


class Colors:
    """ANSI escape codes used by `ColoredFormatter`."""

    GREY = "\x1b[38;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"


class ColoredFormatter(logging.Formatter, Colors):
    """Color each log line by level, for readable output in a terminal.

    Args:
        fmt: A `logging` format string, applied inside the color codes.
    """

    def __init__(self, fmt):
        super().__init__()
        self.fmt = fmt
        self.FORMATS = {
            logging.DEBUG: self.GREY + self.fmt + self.RESET,
            logging.INFO: self.GREEN + self.fmt + self.RESET,
            logging.WARNING: self.YELLOW + self.fmt + self.RESET,
            logging.ERROR: self.RED + self.fmt + self.RESET,
            logging.CRITICAL: self.BOLD_RED + self.fmt + self.RESET,
        }

    def format(self, record):
        """Return the record formatted with its level's color."""
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class JsonFormatter(logging.Formatter):
    """Format each log record as one JSON object per line.

    The object has `timestamp` (ISO 8601, UTC), `level`, `logger` and `message`,
    plus every key passed through `extra=` (such as `job_id` and `worker_id`), and
    `exc_info` when an exception is attached.
    """

    def format(self, record):
        """Return the record as a single-line JSON string."""
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "taskName",
            ] and not key.startswith("_"):
                log_entry[key] = value

        if record.exc_info:
            log_entry["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(log_level=logging.INFO, formatter_type="color"):
    """Configure the root logger for TaskForge's own entry points.

    Call this from applications and scripts (the CLI does it for you). The
    library itself never calls it, so importing TaskForge leaves the host
    application's logging configuration untouched.

    Args:
        log_level: Minimum level for the root logger.
        formatter_type: `"color"` for human-readable lines (plain text when output
            isn't a terminal), or `"json"` for one JSON object per line.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if formatter_type == "json":
        formatter = JsonFormatter()
    else:
        log_format = "%(asctime)s - %(levelname)-8s - %(name)-25s - %(message)s"
        if sys.stdout.isatty():
            formatter = ColoredFormatter(log_format)
        else:
            formatter = logging.Formatter(log_format)

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # SQLAlchemy logs every statement at INFO, which drowns out job logs.
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
