import pytest
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


def test_jobs_processed_counter_increments():
    """Test that the jobs processed counter can be incremented with labels."""
    registry = CollectorRegistry()
    counter = Counter(
        "test_jobs_processed_total",
        "Total jobs processed",
        ["queue", "job_type", "status"],
        registry=registry,
    )

    counter.labels(queue="default", job_type="send_email", status="done").inc()
    counter.labels(queue="default", job_type="send_email", status="done").inc()
    counter.labels(queue="default", job_type="send_email", status="dead").inc()

    assert counter.labels(queue="default", job_type="send_email", status="done")._value.get() == 2.0
    assert counter.labels(queue="default", job_type="send_email", status="dead")._value.get() == 1.0


def test_execution_duration_histogram_observes():
    """Test that the execution duration histogram records observations."""
    registry = CollectorRegistry()
    histogram = Histogram(
        "test_job_duration_seconds",
        "Job execution duration",
        ["queue", "job_type"],
        buckets=(0.1, 0.5, 1.0, 5.0),
        registry=registry,
    )

    histogram.labels(queue="default", job_type="compute").observe(0.25)
    histogram.labels(queue="default", job_type="compute").observe(0.75)
    histogram.labels(queue="default", job_type="compute").observe(3.0)

    # Verify the sum of observations
    sample = histogram.labels(queue="default", job_type="compute")
    assert sample._sum.get() == pytest.approx(4.0, abs=0.01)


def test_queue_depth_gauge_set():
    """Test that the queue depth gauge can be set and read."""
    registry = CollectorRegistry()
    gauge = Gauge(
        "test_queue_depth",
        "Queue depth",
        ["queue", "status"],
        registry=registry,
    )

    gauge.labels(queue="email", status="pending").set(42)
    gauge.labels(queue="email", status="running").set(5)

    assert gauge.labels(queue="email", status="pending")._value.get() == 42.0
    assert gauge.labels(queue="email", status="running")._value.get() == 5.0


def test_active_workers_gauge_inc_dec():
    """Test that the active workers gauge increments and decrements."""
    registry = CollectorRegistry()
    gauge = Gauge(
        "test_active_workers",
        "Active workers",
        ["queue"],
        registry=registry,
    )

    gauge.labels(queue="default").inc()
    gauge.labels(queue="default").inc()
    assert gauge.labels(queue="default")._value.get() == 2.0

    gauge.labels(queue="default").dec()
    assert gauge.labels(queue="default")._value.get() == 1.0
