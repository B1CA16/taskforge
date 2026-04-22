import logging
import threading
from prometheus_client import start_http_server

logger = logging.getLogger(__name__)

_metrics_server_started = False
_lock = threading.Lock()


def start_metrics_server(port: int = 9090):
    """
    Start a lightweight HTTP server to expose Prometheus metrics on /metrics.
    Thread-safe: only starts once even if called multiple times (e.g. multiple workers).
    """
    global _metrics_server_started
    with _lock:
        if _metrics_server_started:
            return
        start_http_server(port)
        _metrics_server_started = True
        logger.info(f"Prometheus metrics server started on port {port}")
