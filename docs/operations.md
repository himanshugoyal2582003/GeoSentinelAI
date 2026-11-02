# Operations Guide

## Local startup

### Backend

```powershell
cd E:\hackfront\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python train_model.py
uvicorn app.main:app --reload --port 8000
```

### Frontend

```powershell
cd E:\hackfront\frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

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
Publish directory: frontend/.next
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

Run:

```powershell
cd E:\hackfront\backend
python train_model.py
```

Confirm `backend/models/change_cnn.pt` exists and restart the API.

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
