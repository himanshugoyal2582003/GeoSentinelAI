# GeoSentinel AI

GeoSentinel is a hackathon MVP for monitoring suspicious quarry expansion from historical and recent satellite imagery.

## What is included

- FastAPI backend with:
  - public Sentinel-2 L2A scene acquisition for the Pune monitoring region;
  - native 10 m COG band reads, NDVI/BSI change signals, and SCL cloud masking;
  - user-defined monitoring polygons with KML/GeoJSON import and custom scans;
  - upload-based image differencing using Pillow and NumPy;
  - connected-component extraction, area estimation, severity scoring, and case-file generation;
  - retry and cached-real-feed handling when the public provider rate-limits requests.
- Next.js dashboard with:
  - automatic live scans every 10 minutes plus manual scan controls;
  - up to eight low-cloud scenes for a multi-point temporal timeline;
  - OpenStreetMap map with finding selection;
  - evidence case-file panel;
  - Google Maps and Google satellite links;
  - explicit live-feed or cached-real-feed labeling;
  - branded scan reports, scheduled site checks, and thresholded email alerts.

## Screenshots

The dashboard combines live or cached Sentinel-2 comparisons, a finding map,
timeline summaries, and downloadable case reports.

![GeoSentinel dashboard](./docs/img/Screenshot%202026-11-02%20211619.png)

![GeoSentinel finding details](./docs/img/Screenshot%202026-11-02%20211632.png)

![GeoSentinel scan workflow](./docs/img/Screenshot%202026-11-02%20211700.png)

## Neo4j Graph Integration

GeoSentinelAI integrates with Neo4j (AuraDB or local instance) for transactional graph persistence, spatial indexing of quarry change findings, and investigation case management:

- **Graph Entities**: `MonitoringRegion`, `Scan`, `SatelliteScene`, `FindingObservation`, `EvidenceAsset`, `InvestigationCase`.
- **Spatial Queries**: Point index on WGS-84 coordinates for spatial proximity queries (`point.distance`).
- **Investigation Intelligence**: Linking multi-temporal observations without premature auto-merging.
- **CSV Migration**: Built-in dry-run, execution, and verification utilities (`backend/scripts/`).
- **Resilience**: Automatic fallback to CSV and graceful degradation if Neo4j is temporarily unreachable.

## Installation and local setup

### Prerequisites

- Python 3.10 or newer
- Node.js 20 or newer and npm
- At least 2 GB of free disk space for Python and PyTorch dependencies

### Backend

```powershell
cd backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The local `backend/.env` configures local CORS. Training is disabled by default
in `.env.example` and in the Render Blueprint because the training endpoint has
no authentication. Set `TRAINING_ENABLED=true` only for a trusted environment
with prepared OSCD data. The local `.env` is ignored by Git.

The checked-in model is a legacy six-channel RGB checkpoint. Phase 3 prepares
OSCD Sentinel-2 multispectral data into ignored local files under
`backend/data/oscd/` and trains a 10-channel model when the dataset is
available. Download and extract the OSCD Images and Train Labels archives,
then run these commands from `backend`:

```powershell
python prepare_oscd.py `
  --source "D:\datasets\Onera Satellite Change Detection dataset - Images" `
  --labels "D:\datasets\Onera Satellite Change Detection dataset - Train Labels"
python train_model.py
```

The training API loads a resulting model at startup and exposes status through
`GET /api/model`. Until OSCD is prepared and trained, the existing six-channel
checkpoint remains supported. The OSCD model scores live multispectral scenes;
it is skipped for RGB-only uploads. OSCD is a general land-cover change
benchmark, not a validated illegal-quarry dataset. See the
[labeling and training guide](./docs/labeling-and-training.md) for details.

Long-term monitoring now includes:

- up to eight low-cloud Sentinel-2 scenes in one scan;
- catalog cloud-cover filtering plus bright-cloud pixel masking;
- FFT phase-correlation image alignment;
- per-channel seasonal/brightness normalization;
- Neo4j scan/finding persistence with CSV recovery fallback in `backend/data/`;
- durable R2 image storage when deployment credentials are configured;
- five-day minimum scheduled site cadence and thresholded operator email alerts;
- `GET /api/scans` for stored scan history and finding tracking.

### Scan the static satellite location

The checked-in six-channel checkpoint loads when the backend starts. To use
the OSCD 10-channel model instead, prepare and train it first as described
above. Start the backend from `backend`:

```powershell
uvicorn app.main:app --reload --port 8000
```

Then either click **LIVE SATELLITE SCAN** in the dashboard or call:

```powershell
Invoke-RestMethod http://localhost:8000/api/live-detect
```

`/api/live-detect` fetches up to eight newest low-cloud Sentinel-2 L2A scenes
from the public Planetary Computer catalog for the static Pune bounding box.
It reads the B02, B03, B04, B08, B11, and SCL COG windows, aligns reflectance
data to a common 10 m UTM grid, and uses NDVI loss, BSI gain, and SCL masking for change signals. RGB images saved
under `/media/` are display previews only. A 10-channel `ChangeCNN` trained
on OSCD supplies an additional live-scene score; the legacy six-channel
checkpoint remains compatible. Findings include georeferenced coordinates.
Sentinel-2 revisits the region approximately every five days; cloudy scenes
are skipped. The dashboard automatically requests a new scan every ten
minutes, subject to provider rate limits.

### Run the frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 for the public overview. The site also includes
pricing and a free-audit request page at http://localhost:3000/pricing, and the
live dashboard at http://localhost:3000/dashboard. Authentication and online
payment are not connected in this MVP. The frontend expects the API at
`http://localhost:8000`; set `NEXT_PUBLIC_API_URL` to override it.

### Verify the setup

With both services running, check the backend:

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

Then open http://localhost:3000/dashboard and select **LIVE SATELLITE SCAN**.

## API documentation

The complete endpoint reference is in
[`docs/api-reference.md`](./docs/api-reference.md). The main endpoints are:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Check API and model availability |
| GET | `/api/model` | Inspect loaded model status and metrics |
| GET | `/api/scans` | Read persisted scan history |
| GET | `/api/live-detect` | Acquire and analyze public Sentinel-2 scenes |
| GET | `/api/sites` | List saved custom monitoring polygons |
| POST | `/api/sites` | Create a monitoring site from GeoJSON |
| POST | `/api/sites/import` | Import a KML or GeoJSON monitoring site |
| POST | `/api/sites/{site_id}/scan` | Acquire and analyze scenes clipped to a site |
| POST | `/api/detect` | Analyze an uploaded historical/recent image pair |
| POST | `/api/train` | Start training when explicitly enabled |
| GET | `/api/train` | Read current training status |

## Security and environment files

Environment files containing local settings or credentials are excluded by
[`.gitignore`](./.gitignore). Only `.env.example` templates are intended for
version control. Before pushing, inspect staged files and scan for accidental
credentials:

```powershell
git status --short
git diff --cached --name-only
git grep -n -I -E '(^|[^A-Za-z])(API_KEY|SECRET|TOKEN|PASSWORD|ACCESS_KEY)='
```

Never put provider keys, access tokens, or private data in source files,
screenshots, CSVs, or documentation. Configure deployment values in the
hosting provider's environment settings.

## Documentation

See the [complete documentation index](./docs/README.md) for the architecture,
working flow, API reference, data model, operations guide, and labeling/training
workflow.

See the [pricing and free-audit guide](./docs/pricing-and-audit.md) for offer
details, current service limits, and Netlify Forms setup.

The generated [architecture diagram](./.github/modernize/assessment/engines/facts/architecture-diagram.md)
shows the application layers and component relationships.

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for development checks and pull
request guidance. GeoSentinel AI is available under the [MIT License](./LICENSE).

### Deploy the backend to Render

The repository includes [`render.yaml`](./render.yaml) for a Render web service.
Create a Blueprint from the repository, or configure a Python web service with:

```text
Root directory: backend
Build command:  pip install -r requirements.txt
Start command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health check:  /api/health
```

Set `CORS_ORIGINS` in Render to the exact browser origin(s) that will call the
API, separated by commas. For example:

```text
CORS_ORIGINS=https://your-site.netlify.app
```

The dashboard's **TRAIN CNN** button calls `/api/train`. The endpoint is
disabled by default in the Render Blueprint because it has no authentication
layer. To train in a trusted environment, temporarily set
`TRAINING_ENABLED=true` and provision prepared OSCD patches under
`backend/data/oscd/`; the dataset is not committed. The model reloads when
training completes. Disable the endpoint again after training.

Local origins remain enabled for development. Do not use `*` with credentials.
Set the frontend build environment variable `NEXT_PUBLIC_API_URL` to the
deployed API URL, for example `https://geosentinel-api.onrender.com`.

Neo4j is the primary durable scan store. Render's local filesystem is
ephemeral: CSV recovery files and local media are not durable across redeploys.
Configure the documented Cloudflare R2 variables for durable scan images and
keep Neo4j credentials configured on both the web service and cron worker.

### Deploy the frontend to Netlify

The repository includes [`netlify.toml`](./netlify.toml). Import the repository
into Netlify and use the detected configuration, or configure:

```text
Base directory: frontend
Build command: npm run build
Publish directory: out
```

Set this Netlify environment variable before building:

```text
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com
```

After Netlify gives the site its public URL, add that exact origin to Render's
`CORS_ORIGINS`, for example:

```text
CORS_ORIGINS=https://your-site.netlify.app
```

If you add a custom frontend domain, include both origins separated by commas.
Redeploy the Render backend after changing `CORS_ORIGINS`.

The pricing page's free-audit form uses Netlify Forms. Confirm that form
detection is enabled for the site and that a test submission appears in the
Netlify dashboard; local development does not store form submissions.

## Upload API

`POST /api/detect` accepts `historical` and `recent` image files. The images must cover the same area and have the same dimensions. The response includes changed components, estimated area, coordinates, and a case report.
