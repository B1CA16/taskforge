"""Smoke-test an *installed* TaskForge, as a user would get it from PyPI.

Run it with the interpreter of a fresh virtual environment where the built wheel
(plus `httpx`, for the test client) is installed:

    pip install dist/*.whl httpx
    python scripts/check_wheel.py

The checks run from an empty temporary directory, so the source checkout can't
mask packaging mistakes. They verify that the package imports from
site-packages, that the dashboard's templates are included, that the dashboard
renders, and that the CLI runs.
"""

import os
import subprocess
import sys
import tempfile
from importlib import metadata, resources
from pathlib import Path


def main() -> int:
    """Run the checks, printing one line per passed check. Returns the exit status."""
    original_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as workdir:
        os.chdir(workdir)
        try:
            run_checks(Path(workdir))
        finally:
            # Windows can't delete the directory while we're in it or while the
            # SQLite file is still open.
            os.chdir(original_cwd)
            if "taskforge.db.base" in sys.modules:
                sys.modules["taskforge.db.base"].reset_engine()
    return 0


def run_checks(workdir: Path) -> None:
    """Run every check; raises `AssertionError` on the first failure."""
    os.environ["TASKFORGE_DATABASE_URL"] = f"sqlite:///{workdir / 'check.db'}"

    import taskforge

    location = Path(taskforge.__file__).resolve()
    assert "site-packages" in location.parts, f"imported from the source tree: {location}"
    print(f"ok  imported taskforge {taskforge.__version__} from {location.parent}")

    installed = metadata.version("taskforge-queue")
    assert taskforge.__version__ == installed, (taskforge.__version__, installed)
    print("ok  __version__ matches the installed distribution")

    templates = resources.files("taskforge.dashboard") / "templates"
    names = sorted(p.name for p in templates.iterdir() if p.name.endswith(".html"))
    for required in ("base.html", "job_detail.html", "jobs.html", "overview.html"):
        assert required in names, f"missing template {required}: found {names}"
    print(f"ok  dashboard templates included: {', '.join(names)}")

    from fastapi.testclient import TestClient

    from taskforge.cli.main import init_db
    from taskforge.dashboard.app import app

    init_db()
    client = TestClient(app)
    for path in ("/", "/jobs", "/api/overview"):
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code, response.text[:300])
    print("ok  dashboard pages and API respond")

    cli = subprocess.run(
        [sys.executable, "-m", "taskforge.cli.main", "--help"],
        capture_output=True,
        text=True,
    )
    assert cli.returncode == 0 and "init-db" in cli.stdout, cli.stderr
    print("ok  CLI runs")


if __name__ == "__main__":
    sys.exit(main())
