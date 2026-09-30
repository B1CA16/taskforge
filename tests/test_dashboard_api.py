import pytest
import datetime
from fastapi.testclient import TestClient
from taskforge.dashboard.app import app
from taskforge.dashboard.dependencies import get_db
from taskforge.task_queue.models import Job, JobStatus, Queue, WorkerRecord, WorkerStatus
from taskforge.db.connection import get_session


@pytest.fixture(scope="function")
def client(db_session):
    """Provide a TestClient with a clean database for each test."""

    def override_get_db():
        with get_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded_db(client):
    """Seed the database with sample data for testing."""
    with get_session() as session:
        queue = Queue(name="test_queue")
        session.add(queue)
        session.commit()

        jobs = [
            Job(type="task_a", queue_id=queue.id, status=JobStatus.pending, tags={"env": "prod"}),
            Job(type="task_a", queue_id=queue.id, status=JobStatus.done, tags={"env": "staging"}),
            Job(type="task_b", queue_id=queue.id, status=JobStatus.dead, error_message="Test error",
                attempts=3, max_attempts=3),
        ]
        session.add_all(jobs)

        worker = WorkerRecord(
            id="worker-test-001",
            hostname="testhost",
            pid=9999,
            status=WorkerStatus.online,
            queues=["test_queue"],
            last_heartbeat_at=datetime.datetime.now(datetime.timezone.utc),
        )
        session.add(worker)
        session.commit()

        return {"queue": queue, "jobs": jobs, "worker": worker}


# --- API Endpoint Tests ---


def test_api_overview(client, seeded_db):
    """Test the /api/overview endpoint returns correct aggregate stats."""
    response = client.get("/api/overview")
    assert response.status_code == 200

    data = response.json()
    assert data["total_jobs"] == 3
    assert data["total_pending"] == 1
    assert data["total_done"] == 1
    assert data["total_dead"] == 1
    assert data["total_workers_online"] == 1
    assert len(data["queues"]) == 1
    assert data["queues"][0]["name"] == "test_queue"


def test_api_list_jobs(client, seeded_db):
    """Test the /api/jobs endpoint returns all jobs."""
    response = client.get("/api/jobs")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3


def test_api_list_jobs_filter_by_status(client, seeded_db):
    """Test filtering jobs by status."""
    response = client.get("/api/jobs?status=pending")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "pending"


def test_api_list_jobs_filter_by_type(client, seeded_db):
    """Test filtering jobs by type."""
    response = client.get("/api/jobs?job_type=task_b")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["type"] == "task_b"


def test_api_list_jobs_filter_by_tag(client, seeded_db):
    """Test filtering jobs by tag key-value pair."""
    response = client.get("/api/jobs?tag_key=env&tag_value=prod")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["tags"]["env"] == "prod"


def test_api_list_jobs_invalid_status(client, seeded_db):
    """Test that an invalid status filter returns 400."""
    response = client.get("/api/jobs?status=invalid")
    assert response.status_code == 400


def test_api_list_jobs_pagination(client, seeded_db):
    """Test job listing respects limit and offset."""
    response = client.get("/api/jobs?limit=1&offset=0")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get("/api/jobs?limit=1&offset=2")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_api_get_job_detail(client, seeded_db):
    """Test getting a single job's full details."""
    # First get a job ID from the list
    jobs = client.get("/api/jobs").json()
    job_id = jobs[0]["id"]

    response = client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == job_id
    assert "payload" in data
    assert "error_message" in data


def test_api_get_job_not_found(client, seeded_db):
    """Test that a nonexistent job returns 404."""
    response = client.get("/api/jobs/nonexistent-id")
    assert response.status_code == 404


def test_api_replay_dead_job(client, seeded_db):
    """Test replaying a dead job via the API."""
    # Find the dead job
    dead_jobs = client.get("/api/jobs?status=dead").json()
    assert len(dead_jobs) == 1
    dead_job_id = dead_jobs[0]["id"]

    # Replay it
    response = client.post(f"/api/jobs/{dead_job_id}/replay")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "pending"
    assert data["type"] == "task_b"
    assert data["id"] != dead_job_id  # New job created


def test_api_replay_non_dead_job_fails(client, seeded_db):
    """Test that replaying a non-dead job returns 400."""
    pending_jobs = client.get("/api/jobs?status=pending").json()
    assert len(pending_jobs) > 0

    response = client.post(f"/api/jobs/{pending_jobs[0]['id']}/replay")
    assert response.status_code == 400


def test_api_list_workers(client, seeded_db):
    """Test the /api/workers endpoint."""
    response = client.get("/api/workers")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "worker-test-001"
    assert data[0]["hostname"] == "testhost"
    assert data[0]["status"] == "online"


def test_api_list_queues(client, seeded_db):
    """Test the /api/queues endpoint."""
    response = client.get("/api/queues")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "test_queue"
    assert data[0]["total"] == 3


# --- Dashboard Page Tests ---


def test_dashboard_overview_page(client, seeded_db):
    """Test that the overview page renders successfully."""
    response = client.get("/")
    assert response.status_code == 200
    assert "TaskForge" in response.text
    assert "test_queue" in response.text


def test_dashboard_jobs_page(client, seeded_db):
    """Test that the jobs page renders successfully."""
    response = client.get("/jobs")
    assert response.status_code == 200
    assert "task_a" in response.text


def test_dashboard_jobs_page_with_filters(client, seeded_db):
    """Test that the jobs page accepts filter query params."""
    response = client.get("/jobs?status=dead")
    assert response.status_code == 200
    assert "task_b" in response.text


def test_dashboard_job_detail_page(client, seeded_db):
    """Test that the job detail page renders."""
    jobs = client.get("/api/jobs").json()
    job_id = jobs[0]["id"]

    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    assert job_id in response.text


def test_dashboard_job_detail_not_found(client, seeded_db):
    """Test that a nonexistent job detail returns 404."""
    response = client.get("/jobs/nonexistent-id")
    assert response.status_code == 404


def test_dashboard_htmx_partial_response(client, seeded_db):
    """Test that HTMX requests return a partial HTML fragment."""
    response = client.get("/jobs", headers={"HX-Request": "true"})
    assert response.status_code == 200
    # Partial should not contain the full base layout
    assert "<aside" not in response.text
    # But should contain the table
    assert "<table>" in response.text
