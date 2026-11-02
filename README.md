# GeoSentinel AI

GeoSentinel is a hackathon MVP for monitoring suspicious quarry expansion from historical and recent satellite imagery.

## What is included

- FastAPI backend with:
  - public Sentinel-2 L2A scene acquisition for the Pune monitoring region;
  - upload-based image differencing using Pillow and NumPy;
  - connected-component extraction, area estimation, severity scoring, and case-file generation;
  - retry and cached-real-feed handling when the public provider rate-limits requests.
- Next.js dashboard with:
  - automatic live scans every 10 minutes plus manual scan controls;
  - up to eight low-cloud scenes for a multi-point temporal timeline;
  - OpenStreetMap map with finding selection;
  - evidence case-file panel;
  - Google Maps and Google satellite links;
  - explicit live-feed or cached-real-feed labeling.

## Run locally

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python train_model.py
uvicorn app.main:app --reload --port 8000
```

`train_model.py` builds a CPU-friendly CNN from the real Sentinel-2 pair,
evaluates it, and writes `backend/models/change_cnn.pt` plus
`backend/models/metrics.json`. The API loads the model on startup and exposes
its status at `GET /api/model`. If the model artifact is absent, image
differencing remains available as an explicit fallback.

Training now uses the real public Sentinel-2 pair in
`dataset/public-sentinel2-pune`. It creates weak labels from measured image
difference tiles. This is a real-image workflow, but it is not a validated
illegal-mining model; production training requires expert-labeled scene pairs.
To add real labels, append rows to `dataset/public-sentinel2-pune/labels.csv`
with `x,y,label` (`label` is `1` for confirmed quarry change and `0` for
stable land), then retrain. The script uses those labels when present.

Long-term monitoring now includes:

- up to eight low-cloud Sentinel-2 scenes in one scan;
- catalog cloud-cover filtering plus bright-cloud pixel masking;
- FFT phase-correlation image alignment;
- per-channel seasonal/brightness normalization;
- CSV history in `backend/data/scans.csv` and `backend/data/findings.csv`;
- `GET /api/scans` for stored scan history and finding tracking.

### Train first, then scan the static satellite location

Start the backend in this order:

```powershell
cd E:\hackfront\backend
python train_model.py
uvicorn app.main:app --reload --port 8000
```

Then either click **LIVE SATELLITE SCAN** in the dashboard or call:

```powershell
Invoke-RestMethod http://localhost:8000/api/live-detect
```

`/api/live-detect` fetches up to eight newest low-cloud Sentinel-2 L2A rendered
previews from the public Planetary Computer catalog for the static Pune
bounding box, saves the historical/recent comparison images under
`/media/`, runs `ChangeCNN`, and returns findings with estimated coordinates.
Sentinel-2 revisits the region approximately every five days; cloudy scenes
are skipped. The dashboard automatically requests a new scan every ten
minutes, subject to provider rate limits.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The frontend expects the API at `http://localhost:8000`; set `NEXT_PUBLIC_API_URL` to override it.

## Documentation

See the [complete documentation index](./docs/README.md) for the architecture,
working flow, API reference, data model, operations guide, and labeling/training
workflow.

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
CORS_ORIGINS=https://geosentinel-ui.onrender.com
```

Local origins remain enabled for development. Do not use `*` with credentials.
Set the frontend build environment variable `NEXT_PUBLIC_API_URL` to the
deployed API URL, for example `https://geosentinel-api.onrender.com`.

Render's default filesystem is ephemeral, so CSV scan history and downloaded
live images are not durable across redeploys or restarts. Add a persistent disk
or move these records to durable storage for production retention.

### Deploy the frontend to Netlify

The repository includes [`netlify.toml`](./netlify.toml). Import the repository
into Netlify and use the detected configuration, or configure:

```text
Base directory: frontend
Build command: npm run build
Publish directory: frontend/.next
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

## Upload API

`POST /api/detect` accepts `historical` and `recent` image files. The images must cover the same area and have the same dimensions. The response includes changed components, estimated area, coordinates, and a case report.
