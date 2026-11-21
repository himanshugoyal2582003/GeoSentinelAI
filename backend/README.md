# Backend

The Python service is a FastAPI application for Sentinel-2 acquisition,
change analysis, scan persistence, reports, and scheduled site monitoring.

## Run locally

From this directory, run:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Configure only local or test values in the ignored `.env`; never commit it.
On Windows, use Python 3.13 for these pinned dependencies and call the venv's
`python.exe` directly so Conda cannot select a different interpreter.
If `.venv` was created with Python 3.14, remove and recreate only that
virtual-environment folder with Python 3.13.

Run tests from this directory with
`.\.venv\Scripts\python.exe -m pytest`. See the root
[`README.md`](../README.md) and [`docs/operations.md`](../docs/operations.md)
for full setup and deployment steps.

## Modules

- [`app/`](./app/) contains API, analysis, persistence, and worker code.
- [`scripts/`](./scripts/) contains Neo4j schema and migration tools.
- [`tests/`](./tests/) contains unit, API, and integration tests.
- [`data/`](./data/) contains CSV recovery data and local runtime outputs.
- [`models/`](./models/) contains the checked-in model and metrics.
