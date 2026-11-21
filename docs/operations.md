# Operations Guide

## Local startup

### Backend

```powershell
cd E:\hackfront\backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

`backend/.env.example` contains local `CORS_ORIGINS` and
`TRAINING_ENABLED=true`. Copy it to `backend/.env`; the actual `.env` file is
ignored by Git. Render does not receive this local file, so configure the same
variables in the Render service environment or through `render.yaml`.

### Frontend

```powershell
cd E:\hackfront\frontend
npm install
npm run dev
```

Open `http://localhost:3000` for the sign-in/sign-up UI preview. Authentication
is not connected in this MVP; open `http://localhost:3000/dashboard` to use the
live dashboard.

## Render deployment

The root [`render.yaml`](../render.yaml) defines the backend service. Create a
Render Blueprint from the repository, then set:

```text
CORS_ORIGINS=https://your-frontend.onrender.com
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
Publish directory: frontend/out
```

Set the Netlify environment variable:

```text
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com
```

After deployment, copy the exact Netlify site origin into Render's
`CORS_ORIGINS` value. Include protocol, omit paths, and separate multiple
origins with commas. Redeploy the backend after changing that variable.

## Operational cadence

- Browser polling: every ten minutes.
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

Set `TRAINING_ENABLED=true` and ensure prepared OSCD patches exist under
`backend/data/oscd/` before starting training. The included Render Blueprint
sets this to `true`, but deployment filesystems may not contain the large
dataset, so training can fail until it is provisioned. The dashboard polls
`/api/train` and reports completion or failure. Disable the variable again
after training for a public production deployment. Do not expose this
unauthenticated endpoint to an untrusted audience.

### Frontend cannot call the API

Check `NEXT_PUBLIC_API_URL`, the backend health endpoint, and `CORS_ORIGINS`.
The CORS value must contain the exact scheme and host of the browser origin,
without a path.

### No durable history on Render

Render's default filesystem is ephemeral. Configure a persistent disk or
replace CSV persistence with durable managed storage before relying on scan
history operationally.

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

In local development, image evidence and diff assets are stored under `backend/data/evidence/`. In production on Render, Render's default filesystem is ephemeral. Evidence assets should be stored in durable object storage (such as AWS S3, Google Cloud Storage, or Azure Blob Storage) with metadata records pointing to the durable URIs.

## Rollback Strategy

If a migration run needs to be rolled back:
```cypher
MATCH (s:Scan {mode: 'historical-csv'}) DETACH DELETE s
MATCH (fo:FindingObservation {review_status: 'migrated'}) DETACH DELETE fo
```
The original CSV files (`scans.csv`, `findings.csv`) are never deleted or modified by migration tools.
