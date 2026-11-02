# API Reference

Base URL locally: `http://localhost:8000`

## `GET /api/health`

Returns service and model availability.

```json
{
  "status": "ok",
  "service": "geosentinel-api",
  "model": "ChangeCNN"
}
```

`model` is `difference-fallback` when the model artifact cannot be loaded.

## `GET /api/model`

Returns whether `change_cnn.pt` loaded and the contents of
`backend/models/metrics.json`.

## `GET /api/scans`

Returns the newest stored scan rows from `backend/data/scans.csv`.

```json
{ "scans": [{ "scan_id": "scan-...", "changed_area_sqm": "1234" }] }
```

CSV values are returned as strings because this endpoint exposes persisted
records.

## `GET /api/live-detect`

Acquires and analyzes public scenes for the fixed Pune bounding box.

### Main response fields

| Field | Meaning |
|---|---|
| `scanId` | CSV persistence identifier for a successful scan |
| `region` | Monitoring region name |
| `historicalDate` / `recentDate` | Dates of the primary comparison pair |
| `findings` | Detected connected components |
| `summary` | Area, hectares, high-risk count, average confidence |
| `timeline` | Adjacent scene-pair area measurements |
| `areaBreakdown` | Finding-level area list |
| `processing` | Threshold, masking, alignment, model metadata |
| `source` | Provider, scene dates, cloud cover, media URLs, cadence |

`source.stale` is `true` when the response is a cached real result. A fresh
successful response does not set this flag.

### Finding shape

```json
{
  "id": "GS-LIVE-SENTINEL2-001",
  "label": "Detected change 1",
  "areaName": "Example area",
  "severity": "high",
  "confidence": 0.81,
  "areaSqm": 4200,
  "coordinates": [18.52, 73.86],
  "regionBbox": [18.51, 73.85, 18.53, 73.87],
  "detectionErrorSqm": 700,
  "googleMapsUrl": "https://www.google.com/maps/...",
  "googleSatelliteUrl": "https://www.google.com/maps/@?...",
  "changeType": "Spectral surface change",
  "status": "Needs review"
}
```

The example values illustrate the shape only; the service calculates actual
values at runtime.

## `POST /api/detect`

Multipart upload endpoint.

Required fields:

- `historical`: image file.
- `recent`: image file.

Optional query parameters:

- `latitude` (default `18.5204`)
- `longitude` (default `73.8567`)
- `pixel_size_m` (default `10`)

Both images must be readable RGB images with identical dimensions and no more
than four megapixels each. The endpoint returns the analysis response shape
without live source metadata.

## `POST /api/train`

Starts asynchronous CNN training from the committed dataset. The endpoint
returns immediately with a training state. It is available only when the
backend environment variable `TRAINING_ENABLED=true`.

## `GET /api/train`

Returns the current training state:

```json
{
  "status": "running",
  "message": "CNN training is running."
}
```

When complete, the backend reloads `change_cnn.pt`. Training is disabled by
default on Render and should only be enabled temporarily for an authorized
operator; this endpoint has no user authentication layer.

## CORS

The backend always allows:

- `http://localhost:3000`
- `http://127.0.0.1:3000`

Additional exact origins are read from `CORS_ORIGINS`, comma-separated. Origins
are normalized by trimming whitespace and trailing slashes. Wildcard CORS is
not used.

## Media

`/media/historical-live.png` and `/media/recent-live.png` serve the latest
downloaded comparison images from the backend media directory.
