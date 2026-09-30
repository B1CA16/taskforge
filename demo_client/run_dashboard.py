import os
import sys

# Adjust sys.path to include the project's 'src' directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import uvicorn

if __name__ == "__main__":
    print("--- Starting TaskForge Dashboard ---")
    print("Open http://localhost:8000 in your browser")
    print("API docs available at http://localhost:8000/docs")
    print("Press Ctrl+C to stop.")
    uvicorn.run(
        "taskforge.dashboard.app:app",
        host="127.0.0.1",  # local only: the dashboard has no authentication yet
        port=8000,
        reload=True,
    )
