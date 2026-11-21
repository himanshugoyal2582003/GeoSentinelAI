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


## `GET /api/health/ready`

Readiness probe for zero-downtime deployments and orchestrators.
Returns `200 OK` if the Neo4j database is reachable; returns `503 Service Unavailable` if the database cannot be contacted. Never claims readiness when Neo4j writes cannot succeed.

```json
{
  "status": "ready",
  "service": "geosentinel-api",
  "database": "connected"
}
```

## `POST /api/live-detect`

Preferred live acquisition, analysis, and graph persistence endpoint.
Accepts an optional `Idempotency-Key` header. Performs live Sentinel-2 satellite scene acquisition, runs change detection and CNN inference, and persists the full graph structure (Scan, Scenes, Observations, Region) transactionally into Neo4j.

Returns the standard detection result with `scanId` and `source` metadata.

> Note: `GET /api/live-detect` is retained as a backward-compatible alias and returns an `X-Deprecated: Use POST /api/live-detect instead` header.

## `GET /api/scans/{scan_id}`

Retrieves a single persisted scan by its `scan_id`. Returns `404 Not Found` if missing.

```json
{
  "scan_id": "scan-20250101120000-aabbcc",
  "mode": "live-sentinel2",
  "status": "completed",
  "historical_date": "2025-01-01",
  "recent_date": "2025-10-01",
  "changed_area_sqm": 15000,
  "finding_count": 3,
  "model_name": "ChangeCNN"
}
```

## `GET /api/findings/{detection_id}`

Retrieves details for a single `FindingObservation` node by its unique detection ID.

```json
{
  "detection_id": "det-scan-001-GS-LIVE-001",
  "original_finding_id": "GS-LIVE-001",
  "scan_id": "scan-001",
  "label": "Detected change 1",
  "severity": "high",
  "confidence": 0.88,
  "area_sqm": 12500,
  "latitude": 18.52,
  "longitude": 73.86,
  "review_status": "pending"
}
```

## `GET /api/findings/{detection_id}/history`

Spatial query finding other observations within a configurable radius across different scans.

Query parameters:
- `radius_m`: Search radius in metres (default: `500.0`, range `10.0` - `10000.0`).

```json
{
  "detection_id": "det-scan-001-GS-LIVE-001",
  "radius_m": 500.0,
  "related_observations": [
    {
      "detection_id": "det-scan-002-GS-LIVE-001",
      "distance_m": 42.5,
      "confidence": 0.85,
      "last_observed": "2025-11-01"
    }
  ]
}
```

## `GET /api/graph/regions/{region_id}`

Retrieves the monitoring region graph entity and its linked scan history.

Query parameters:
- `limit`: Max scans to return (default: `20`, max: `100`)
- `offset`: Pagination offset (default: `0`)

## `GET /api/graph/findings/{detection_id}/recommendations`

Recommends candidate observations across different scans for human investigator review based on spatial proximity. Does not auto-merge observations.

## `GET /api/investigations`

Lists human review investigation cases with associated observation counts.

Query parameters:
- `limit`: Default `50`, max `200`
- `offset`: Default `0`

## `POST /api/investigations`

Creates a new investigation case.

Request body:
```json
{
  "title": "Wagholi Pit Expansion Q3",
  "description": "Suspicious perimeter growth near secondary road",
  "status": "open",
  "review_status": "pending"
}
```

## `GET /api/investigations/{case_id}`

Retrieves an investigation case and its array of linked finding observations.

## `POST /api/investigations/{case_id}/observations`

Associates a finding observation with an investigation case. Prevents duplicate relationships.

Request body:
```json
{
  "detection_id": "det-scan-001-GS-LIVE-001"
}
```
