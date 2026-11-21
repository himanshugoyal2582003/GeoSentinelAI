# System Architecture

## Context

GeoSentinel AI has two runtime applications:

- **Frontend:** Next.js sign-in/sign-up preview and dashboard served to a
  browser. Authentication is not connected in this MVP.
- **Backend:** FastAPI service that acquires public imagery, performs analysis,
  persists scans to Neo4j with CSV fallback, and serves media and JSON results.

External services are public or browser-facing:

- Microsoft Planetary Computer STAC and signed preview assets.
- Nominatim reverse geocoding.
- OpenStreetMap tiles in the browser.
- Google Maps links opened from finding reports.

```mermaid
flowchart LR
    Browser[Next.js dashboard] -->|JSON/CORS| API[FastAPI backend]
    Browser -->|Map tiles| OSM[OpenStreetMap]
    Browser -->|Open links| Google[Google Maps / Satellite]
    API -->|STAC search + signed COG windows| MPC[Microsoft Planetary Computer]
    API -->|Reverse geocode| Nominatim[Nominatim]
    API -->|Read/write| Files[(PNG cache + CSV fallback + model)]
    API -->|Graph persistence| Neo4j[(Neo4j)]
```

## Repository structure

```text
backend/
  app/main.py              FastAPI routes and image-processing pipeline
  app/api/sites.py         Custom monitoring-site API
  app/geometry.py          GeoJSON/KML validation and geometry conversion
  app/satellite_cog.py     Windowed Sentinel-2 COG reads and raster georeferencing
  app/model_config.py      Shared Sentinel-2 model band and channel definitions
  app/change_model.py      ChangeCNN definition and model loading
  app/history.py           CSV scan/finding fallback persistence
  prepare_oscd.py          OSCD multispectral pair/mask conversion to patches
  train_model.py           Memory-mapped supervised training and metrics
  models/                  change_cnn.pt and metrics.json
  data/                    scans.csv, findings.csv, live cache/media
dataset/
  public-sentinel2-pune/   Real preview pair, manifest, labels.csv
frontend/
  app/page.tsx             Sign-in/sign-up UI preview (no auth backend)
  app/dashboard/page.tsx   Dashboard, scan actions, map, reports
  app/globals.css          Dashboard styling
  app/layout.tsx           Metadata and shell
render.yaml                Render backend service definition
```

## Backend boundaries

### Acquisition

`_live_scenes()` posts a STAC search for the static bounding box, filters
scenes with `eo:cloud_cover < 20`, sorts by acquisition time, and retains the
newest eight. `read_sentinel2_scene()` signs and window-reads each B02, B03,
B04, B08, B11, and SCL COG asset, resampling into one 10 m UTM grid. Assets
with no valid pixels in the requested region are rejected.
Custom site scans search the site's WGS-84 bounding box and mask every raster
band to the exact polygon before analysis. The grid is limited to four million
pixels per scan.

### Analysis

`_analyse_pair()` performs the following sequence:

1. Make RGB display previews and align scene pairs with FFT phase correlation.
2. Derive NDVI and Bare Soil Index (BSI) from scaled reflectance bands.
3. Mask SCL no-data, shadow, unclassified, cloud, cirrus, and snow classes.
4. Flag NDVI loss or BSI gain above the configured minimum/90th-percentile
   change threshold.
5. Estimate component coordinates from the UTM raster transform.
6. Score each finding with the compatible six-channel RGB checkpoint or,
   after OSCD training, the ten-channel multispectral model.
7. Connected-component extraction with a minimum component size.
8. Area, confidence, severity, coordinates, bounding box, and map links from
   the georeferenced raster grid.

The 10-channel model is skipped for RGB-only uploads. OSCD models land-cover
change and is not trained to identify illegal quarry activity.

The latest pair supplies the main findings. Adjacent pairs supply timeline
points. At most ten components are returned per pair.

### Persistence

Successful scans are written transactionally to Neo4j. If graph persistence
fails, records are written to the CSV fallback:

- `backend/data/scans.csv`
- `backend/data/findings.csv`

The latest result and two display-preview images are written under
`backend/data/live/`. If the provider rate-limits or another acquisition error
occurs, `last-result.json` is returned with `source.stale: true` when available.

## Frontend boundaries

The dashboard:

- calls `/api/live-detect` on initial load;
- calls it manually from **LIVE SATELLITE SCAN**;
- calls it automatically every ten minutes while the page is open;
- displays live or cached-real-feed status;
- renders the two comparison images;
- renders findings on OpenStreetMap;
- opens Google Maps and Google satellite links;
- downloads a JSON case report in the browser.

The ten-minute interval is an application polling interval. It does not create
new satellite imagery; Sentinel-2 observations are naturally available at an
approximately five-day revisit cadence and cloudy observations can be skipped.

## Deployment topology

Render runs the backend from the `backend` root:

```text
Build:  pip install -r requirements.txt
Start:  uvicorn app.main:app --host 0.0.0.0 --port $PORT
Check:  /api/health
```

The frontend can be deployed separately and must set
`NEXT_PUBLIC_API_URL` to the backend URL. The backend accepts localhost origins
and additional exact origins from `CORS_ORIGINS`.

