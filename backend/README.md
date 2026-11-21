# Backend

The Python service is a FastAPI application for Sentinel-2 acquisition,
change analysis, scan persistence, reports, and scheduled site monitoring.

## Run locally

From this directory, run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Configure only local or test values in the ignored `.env`; never commit it.

Run tests from this directory with `python -m pytest`. See the root
[`README.md`](../README.md) and [`docs/operations.md`](../docs/operations.md)
for full setup and deployment steps.

## Modules

- [`app/`](./app/) contains API, analysis, persistence, and worker code.
- [`scripts/`](./scripts/) contains Neo4j schema and migration tools.
- [`tests/`](./tests/) contains unit, API, and integration tests.
- [`data/`](./data/) contains CSV recovery data and local runtime outputs.
- [`models/`](./models/) contains the checked-in model and metrics.
