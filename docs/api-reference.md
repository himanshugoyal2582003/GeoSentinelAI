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
`backend/models/metrics.json`. The response also includes `miningFootprintModel`
with the loading status and metrics for `mine_footprint_cnn.pt`, when trained.

The response includes `inputChannels` (`6` for the legacy RGB checkpoint or
`10` for the trained multispectral model) and the model metrics. A 10-channel
model is applied only to live Sentinel-2 scenes; RGB uploads are skipped.

## `GET /api/scans`

Returns newest stored scan rows from Neo4j, falling back to
`backend/data/scans.csv` when Neo4j is unavailable. Supports `limit` (1-200),
`offset` (0 or greater), and optional `region_id`.

```json
{
  "scans": [{ "scan_id": "scan-...", "changed_area_sqm": "1234" }],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

Fallback CSV values are returned as strings because this endpoint exposes
persisted records.

## `GET /api/live-detect`

Returns a cached or newly acquired analysis of public scenes for the fixed
Pune bounding box. Automatic requests reuse a successful result for up to 30
minutes to limit catalog traffic.

The dashboard uses `GET` for automatic refreshes. An explicit `POST` requests a
fresh acquisition and bypasses the shared cache.

### Main response fields

| Field | Meaning |
|---|---|
| `scanId` | Persistence identifier for a successful scan (Neo4j, with CSV fallback) |
| `region` | Monitoring region name |
| `historicalDate` / `recentDate` | Dates of the primary comparison pair |
| `findings` | Detected connected components |
| `summary` | Area, hectares, high-risk count, average confidence |
| `timeline` | Adjacent scene-pair area measurements |
| `areaBreakdown` | Finding-level area list |
| `processing` | Reflectance bands/indices, threshold, SCL masking, alignment, and model metadata |
| `source` | Provider, scene dates, cloud cover, 10 m COG resolution, media URLs, cadence |

`source.stale` is `true` when the response is a cached real result.
`source.cacheAgeSeconds` gives the age of any cached result. Results younger
than 30 minutes satisfy the shared cache; an older result may be served after
an acquisition failure or during its retry cooldown. A fresh successful
response does not set these cache fields.

## Custom monitoring sites

Sites are stored as `MonitoringRegion` nodes in Neo4j. Geometry must be a
valid GeoJSON `Polygon` or `MultiPolygon` in WGS-84 longitude/latitude order.
The API limits imports to 2 MB and geometries to 5,000 vertices. Antimeridian
crossings are not supported; sites must fit within UTM latitudes (-80° to
84°). Site scans are capped at four million 10 m grid pixels.

### `GET /api/sites`

Lists active sites. Supports `limit` (1-200) and `offset` (0 or greater).

### `POST /api/sites`

Creates a site from a GeoJSON geometry:

```json
{
  "name": "North quarry",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[73.82, 18.48], [73.86, 18.48], [73.86, 18.52], [73.82, 18.52], [73.82, 18.48]]]
  }
}
```

### `POST /api/sites/import`

Multipart upload with a required `name` and `file` (`.kml`, `.geojson`, or
`.json`). GeoJSON `Feature`, `FeatureCollection`, `Polygon`, and `MultiPolygon`
uploads are accepted; KML Polygon boundaries are converted to GeoJSON.

### `GET /api/sites/{site_id}` / `DELETE /api/sites/{site_id}`

Retrieves or deactivates a site. Deletion is soft so existing scan history is
preserved.

### `POST /api/sites/{site_id}/scan`

Searches Sentinel-2 scenes for the site's bounding box, then masks analysis to
the exact polygon. The result uses the standard detection response and records
the site ID and boundary geometry. An `Idempotency-Key` header is optional.

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

Starts asynchronous OSCD CNN training from prepared patches in
`backend/data/oscd/`. The endpoint returns immediately with a training state.
It is available only when the backend environment variable
`TRAINING_ENABLED=true`. It is disabled by default in the sample environment
and Render Blueprint because the endpoint is unauthenticated. It reports
failure if OSCD preparation has not been run.

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

## `POST /api/train/mining`

Starts training the separate mine-footprint segmentation model from the
prepared public dataset under `backend/data/public_mining`. The backend must
have `TRAINING_ENABLED=true`; the dataset's image and mask preparation steps
are documented in `dataset/public-global-mining/README.md`.

## `GET /api/train/mining`

Returns the mining model training state. On completion the API reloads
`mine_footprint_cnn.pt`. This model estimates mining footprint pixels and does
not classify illegality or temporal expansion.

## CORS

The backend always allows:

- `http://localhost:3000`
- `http://127.0.0.1:3000`

Additional exact origins are read from `CORS_ORIGINS`, comma-separated. Origins
are normalized by trimming whitespace and trailing slashes. Wildcard CORS is
not used.

## Media

`/media/historical-{capture_id}.png` and `/media/recent-{capture_id}.png`
serve scan-specific comparison images from the backend media directory. These
are used to avoid attaching a later scan's imagery to an earlier report.


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

## `GET /api/scans/{scan_id}/report.pdf`

Downloads a one-page branded screening report for a persisted scan. The report
includes the selected finding, observation dates, changed area, cloud-mask
status, before/after scan-specific image crops with overlays when available,
and a Google Satellite link. If Neo4j is unavailable, the endpoint can also
retrieve scans written to the CSV fallback.

Query parameters:

- `template`: `quarry-compliance` (default) or `landowner-evidence`.
- `brand_name`: report header/author, 1-80 characters (default `GeoSentinel AI`).
- `finding_id`: optional original finding ID; defaults to the scan's first finding.

Returns `application/pdf`; unknown scans or findings return `404`, and
unavailable report storage returns `503`. The report is a screening aid, not a
legal determination or a substitute for field verification.

## `GET /api/scans/{scan_id}/images/{kind}`

Streams the stored scan preview (`kind` is `historical` or `recent`). The
backend reads from the configured evidence storage provider; older scans may
use their existing local preview when available.

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

## `PUT /api/investigations/{case_id}` / `PATCH /api/investigations/{case_id}`

Updates status (`open`, `investigating`, `closed`), `review_status`, or `description` for a case.

## `POST /api/auth/login`

Authenticates credentials and returns a signed Bearer token with session idle tracking.

Request body:
```json
{
  "username": "admin",
  "password": "geosentinel-admin"
}
```

Response:
```json
{
  "access_token": "geo_...",
  "token_type": "Bearer",
  "username": "admin",
  "idle_timeout_seconds": 900,
  "expires_in": 86400
}
```

## `GET /api/auth/me`

Validates the Bearer token, checks idle session inactivity, and refreshes the activity timestamp.

Header: `Authorization: Bearer <access_token>`

If the user is inactive for longer than `idle_timeout_seconds` (15 minutes), the server responds with:
`401 Unauthorized: Session expired due to idle inactivity. Please log in again.`

## `POST /api/auth/logout`

Revokes the active Bearer token immediately.

