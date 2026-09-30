import logging
import os
import threading

from prometheus_client import start_http_server

logger = logging.getLogger(__name__)

# 9090 is Prometheus' own default port, so we stay clear of it.
DEFAULT_METRICS_PORT = 9464

_metrics_server_started = False
_lock = threading.Lock()


def resolve_metrics_port(port: int | None = None) -> int:
    """Return ``port``, else ``TASKFORGE_METRICS_PORT``, else the default."""
    if port is not None:
        return port
    return int(os.getenv("TASKFORGE_METRICS_PORT", DEFAULT_METRICS_PORT))


def start_metrics_server(port: int | None = None) -> bool:
    """Expose Prometheus metrics on ``http://0.0.0.0:<port>/metrics``.

    Starts at most once per process (several ``Worker`` objects in one process
    share the exporter). If the port is taken, e.g. by another worker process on
    the same host, a warning is logged and the worker keeps running without
    an exporter.

    Returns:
        True if the exporter is running in this process.
    """
    global _metrics_server_started
    port = resolve_metrics_port(port)
    with _lock:
        if _metrics_server_started:
            return True
        try:
            start_http_server(port)
        except OSError as exc:
            logger.warning(
                f"Could not start Prometheus metrics server on port {port}: {exc}. "
                "Set a different port with TASKFORGE_METRICS_PORT or Worker(metrics_port=...).",
                extra={"metrics_port": port},
            )
            return False
        _metrics_server_started = True
        logger.info(f"Prometheus metrics server started on port {port}")
        return True
