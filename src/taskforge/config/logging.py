import logging
import json
import sys
from datetime import datetime, timezone

class JsonFormatter(logging.Formatter):
    """
    Formats log records as a JSON string.
    """
    def format(self, record):
        # Create a dictionary from the log record
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Dynamically add all extra attributes
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename', 'module',
                           'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName', 'created', 'msecs',
                           'relativeCreated', 'thread', 'threadName', 'processName', 'process', 'taskName'] and not key.startswith('_'):
                # Convert datetime objects to ISO format if they are found in extra fields
                if isinstance(value, datetime):
                    log_entry[key] = value.isoformat()
                else:
                    log_entry[key] = value

        # Add exception info if present
        if record.exc_info:
            log_entry['exc_info'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)

def setup_logging(log_level=logging.INFO):
    """
    Sets up a centralized, structured logger for the entire application.
    This function should be called once when the application starts.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove any existing handlers to prevent duplication
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    formatter = JsonFormatter()
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Capture logs from SQLAlchemy and route them through our handlers
    # Set the level to WARNING to avoid seeing every single SQL statement.
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)

# Call setup on import to ensure logging is configured
setup_logging()
