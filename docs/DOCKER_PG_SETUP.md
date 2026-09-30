# Docker PostgreSQL Setup for TaskForge (Windows)

## Overview

This guide explains how to set up a clean PostgreSQL instance in Docker on Windows for the **TaskForge** project, configure environment variables, and connect using **Python** and **pgAdmin**.

---

## 1. Remove old container and volumes

If you already have a container or old volumes, remove them to avoid password conflicts:

```powershell
# Stop and remove the old container
docker rm -f taskforge-postgres

# Remove unused Docker volumes (be careful: this deletes all dangling volumes)
docker volume prune -f
```

## 2. Run a new PostgreSQL container

Use a single command in **PowerShell**:

```powershell
docker run --name taskforge-postgres -e POSTGRES_PASSWORD=postgres -p 5435:5432 -d postgres:15
```

> Note: Use port 5435 in your connections because of the port mapping.

---

## 3. Test connection inside Docker

Check that Postgres is running:

```powershell
docker exec -it taskforge-postgres psql -U postgres
```

-   Password: `postgres`
-   If you can connect, the container works correctly.

---

## 4. Configure Python `.env`

Create a `.env` file in the root of your project:

```
TASKFORGE_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5435/postgres

```

> Use 127.0.0.1 (IPv4) instead of localhost to avoid potential IPv6 issues on Windows.

---

## 5. Create the tables

From the root of your project, with the virtual environment active (`pip install -e ".[dev]"` puts `src/` on the path, so there's no need to set `PYTHONPATH`):

```powershell
python -m taskforge.cli.main init-db
```

-   This creates any missing TaskForge tables. It never drops or alters existing ones.
-   No authentication or timeout errors should occur.

> **Running the test suite?** Don't use this database: the tests drop all tables.
> Use the disposable one instead: `docker compose up -d test-db` (port 5436).

---

## 6. Connect with pgAdmin

1. Open pgAdmin and create a new server connection:
    - Host: `127.0.0.1`
    - Port: `5435`
    - Username: `postgres`
    - Password: `postgres`
2. Save and expand the server in pgAdmin.
3. Navigate to **Databases → postgres → Schemas → public → Tables** to verify the tables created by Python.
