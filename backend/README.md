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

## Deploy the API to Fly.io

The backend has its own [fly.toml](./fly.toml), [Dockerfile](./Dockerfile),
and [.dockerignore](./.dockerignore). From this directory, set `app` in
`fly.toml` to a name available in your Fly.io organization, then run:

```sh
fly launch --no-deploy
fly secrets set NEO4J_URI="bolt+s://<your-instance>.databases.neo4j.io" \
  NEO4J_USERNAME="neo4j" NEO4J_PASSWORD="<your-password>" \
  CLOUDFLARE_R2_ACCOUNT_ID="<account-id>" \
  CLOUDFLARE_R2_ACCESS_KEY_ID="<access-key>" \
  CLOUDFLARE_R2_SECRET_ACCESS_KEY="<secret-key>" \
  CLOUDFLARE_R2_BUCKET="<bucket>"
fly secrets set CORS_ORIGINS="https://<your-frontend-domain>"
fly deploy
```

The Fly configuration runs only the API. Set the frontend origin in
`CORS_ORIGINS`; keep training disabled unless the service is protected. The
`bom` region is Mumbai. Fly's root filesystem is ephemeral, so the config uses
Cloudflare R2 for evidence images and Neo4j for durable application records.
Configure both before using the deployed API. Scheduled scans need a separate
scheduled worker; this file deploys the web service only.

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
