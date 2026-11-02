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

## Upload API

`POST /api/detect` accepts `historical` and `recent` image files. The images must cover the same area and have the same dimensions. The response includes changed components, estimated area, coordinates, and a case report.
