"""Prometheus metric objects, shared by every worker in a process.

Metric names are prefixed `taskforge_`. Labels are kept low-cardinality (queue, job
type, status), never per-job or per-worker ids.
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# --- Counters ---

jobs_processed_total = Counter(
    "taskforge_jobs_processed_total",
    "Total number of jobs processed",
    ["queue", "job_type", "status"],
)

jobs_enqueued_total = Counter(
    "taskforge_jobs_enqueued_total",
    "Total number of jobs enqueued",
    ["queue", "job_type"],
)

# --- Histograms ---

job_execution_duration_seconds = Histogram(
    "taskforge_job_execution_duration_seconds",
    "Time spent executing a job",
    ["queue", "job_type"],
    # From 10 ms to 5 min: background jobs range from quick API calls to reports.
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

# --- Gauges ---

queue_depth = Gauge(
    "taskforge_queue_depth",
    "Current number of jobs in a given state",
    ["queue", "status"],
)

active_workers = Gauge(
    "taskforge_active_workers",
    "Number of currently active workers",
    ["queue"],
)

# --- Info ---

worker_info = Info(
    "taskforge_worker",
    "Worker metadata",
)
