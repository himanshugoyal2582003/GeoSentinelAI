# Operations Guide

## Local startup

Run the following commands from the repository root.

### Backend

```powershell
Set-Location .\backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

`backend/.env.example` contains local `CORS_ORIGINS` and sets
`TRAINING_ENABLED=false`. Copy it to `backend/.env`; the actual `.env` file is
ignored by Git. Training is disabled unless you explicitly enable it in a
trusted environment with prepared OSCD data. Render does not receive this local
file, so configure deployment variables in the Render service environment.

### Frontend

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Open `http://localhost:3000` for the public overview,
`http://localhost:3000/pricing` for pricing and the free-audit request, or
`http://localhost:3000/dashboard` for the live dashboard. Authentication and
online payment are not connected in this MVP.

## Render deployment

The root [`render.yaml`](../render.yaml) defines the backend service. Create a
Render Blueprint from the repository, then set `CORS_ORIGINS` to the exact
deployed frontend origin(s), without a path. For example:

```text
CORS_ORIGINS=https://your-site.netlify.app
```

For a separately hosted frontend, set its build-time variable:

```text
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com
```

Verify:

```text
https://your-backend.onrender.com/api/health
```

## Netlify deployment

The root [`netlify.toml`](../netlify.toml) configures the Next.js frontend.
Import the repository into Netlify and set:

```text
Base directory: frontend
Build command: npm run build
Publish directory: out
```

Set the Netlify environment variable:

```text
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com
```

After deployment, copy the exact Netlify site origin into Render's
`CORS_ORIGINS` value. Include protocol, omit paths, and separate multiple
origins with commas. Redeploy the backend after changing that variable.
The free-audit form is collected by Netlify Forms; verify form detection is
enabled and that a test submission appears in the Netlify dashboard. Local
development does not store form submissions.

## Scheduled scans, evidence storage, and alerts

The Render Blueprint defines a daily cron worker. It checks active polygon
sites and scans each one when its most recent scan is at least five days old.
The daily check avoids calendar-month drift from a `*/5` cron expression;
regular browser polling remains independent.

Neo4j AuraDB remains the primary durable database. CSV is a local/recovery
fallback and is not durable across Render redeploys. The cron worker requires
the same `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, and `NEO4J_DATABASE`
settings as the web service.

The Render Blueprint selects Cloudflare R2. Configure these private service
environment variables on both the web service and cron worker:

- `CLOUDFLARE_R2_ACCOUNT_ID`
- `CLOUDFLARE_R2_ACCESS_KEY_ID`
- `CLOUDFLARE_R2_SECRET_ACCESS_KEY`
- `CLOUDFLARE_R2_BUCKET`

`EVIDENCE_STORAGE_PROVIDER=cloudflare-r2` stores historical/recent scan
previews in R2; the API serves them through `/api/scans/{scan_id}/images/{kind}`.
For local development, set `EVIDENCE_STORAGE_PROVIDER=local` (the default).
If an R2 write fails during a live scan, the backend logs the failure and may
serve a clearly marked cached result; it does not mark the new scan as fresh.

Scheduled alerts use the Brevo transactional email API and one operator
recipient. Configure these private variables on the cron worker:

- `BREVO_API_KEY`
- `BREVO_FROM_EMAIL`
- `ALERT_TO_EMAIL`
- Optional `BREVO_FROM_NAME` (defaults to `GeoSentinel AI`)

An alert is queued only for a fresh scan with recorded cloud-mask coverage
below 20%, a finding area of at least 1,000 m², and confidence of at least 80%.
Notifications are recorded in Neo4j and retried after delivery failures.
Recipients are global for this initial phase; do not put credentials in the
repository or expose them through the frontend.

## Operational cadence

- Browser polling: every ten minutes.
- Scheduled polygon scans: no more often than every five days.
- Render worker due-site check: daily at 03:00 UTC.
- Catalog selection: up to eight newest scenes.
- Catalog cloud filter: below 20%.
- Expected Sentinel-2 revisit opportunity: approximately five days.
- Provider rate limits: retries use exponential waits; cached result is used
  when possible.

## Troubleshooting

### HTTP 429

Wait before manually scanning again. The backend retries requests and returns
the latest cached real result when available. The UI labels this response
`CACHED REAL FEED`.

### Model shows `difference-fallback`

The checked-in six-channel checkpoint is used until a new model is trained.
To train the 10-channel OSCD model, first download and extract the OSCD Images
and Train Labels archives, then follow the preparation commands in
[`labeling-and-training.md`](./labeling-and-training.md). Running the trainer
without prepared OSCD data fails explicitly.

Confirm `backend/models/change_cnn.pt` exists and restart the API if it is
missing or invalid.

### Train the CNN from the dashboard

The **TRAIN CNN** button starts the same workflow as:

```powershell
python backend\train_model.py
```

The Render Blueprint sets `TRAINING_ENABLED=false`. In a trusted environment
only, temporarily set it to `true` and ensure prepared OSCD patches exist under
`backend/data/oscd/` before starting training. Deployment filesystems may not
contain the large dataset, so provision it before enabling training. The
dashboard polls `/api/train` and reports completion or failure. Set the value
back to `false` after training. Do not expose this unauthenticated endpoint to
an untrusted audience.

### Frontend cannot call the API

Check `NEXT_PUBLIC_API_URL`, the backend health endpoint, and `CORS_ORIGINS`.
The CORS value must contain the exact scheme and host of the browser origin,
without a path.

### Scheduled scans or alerts are missing

Confirm the cron worker is deployed and check its job logs. Verify Neo4j,
Cloudflare R2, and Brevo environment variables are configured on the cron
service. Sites with a recent scan are intentionally skipped; alerts are not
sent for cached, cloudy, or below-threshold results.

### Area name is a fallback

Nominatim may be unavailable or rate-limited. The backend then returns a
coordinate-based Pune monitoring-area fallback. Coordinates and map links
remain available.

## Safety and interpretation

Detections are spectral surface-change signals. They can be caused by clouds,
seasonality, registration errors, construction, agriculture, quarry activity,
or other land-use changes. Review imagery, permits, and field evidence before
enforcement or public claims.


## Neo4j AuraDB Setup

1. Create a free or paid instance on [Neo4j AuraDB](https://neo4j.com/cloud/platform/aura-graph-database/).
2. Note the generated connection URI (e.g., `bolt+s://<instance-id>.databases.neo4j.io`), username (`neo4j`), and password.
3. Configure these environment variables in your backend `.env` or deployment platform:
   - `NEO4J_URI`
   - `NEO4J_USERNAME`
   - `NEO4J_PASSWORD`
   - `NEO4J_DATABASE` (default: `neo4j`)
4. Verify connectivity using `GET /api/health/ready`.

## Schema Initialization

Run the idempotent schema initializer before first using Neo4j:

```powershell
python scripts/init_neo4j_schema.py
```

This creates uniqueness constraints and spatial point indexes on `FindingObservation.location`. It is safe to run repeatedly.

## CSV Migration and Verification

To migrate historical scans and findings from CSV to Neo4j:

1. **Perform a dry run first**:
   ```powershell
   python scripts/migrate_csv_to_neo4j.py --dry-run
   ```
2. **Execute the migration**:
   ```powershell
   python scripts/migrate_csv_to_neo4j.py
   ```
3. **Verify graph data integrity**:
   ```powershell
   python scripts/verify_migration.py
   ```

## Evidence Storage

Local evidence is stored under `backend/data/evidence/`. The Render Blueprint
selects Cloudflare R2 for scan previews; configure the R2 variables listed
above on both services. Render's local filesystem is ephemeral, so CSV
recovery files and local media are not durable across redeploys. Neo4j remains
the primary durable scan database.

## Rollback Strategy

If a migration run needs to be rolled back:
```cypher
MATCH (s:Scan {mode: 'historical-csv'}) DETACH DELETE s
MATCH (fo:FindingObservation {review_status: 'migrated'}) DETACH DELETE fo
```
The original CSV files (`scans.csv`, `findings.csv`) are never deleted or modified by migration tools.
