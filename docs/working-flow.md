# Working Flow

## 1. User opens the application

1. The browser loads the sign-in/sign-up UI at `/`. Authentication is not
   connected; the form does not send or store credentials.
2. The user opens the public live demo at `/dashboard`.
3. The dashboard requests `GET /api/live-detect`.
4. The backend searches the public Sentinel-2 catalog.
5. The dashboard shows the latest pair, findings, timeline, and map.
6. If acquisition is rate-limited but a prior result exists, the page displays
   the cached real result and labels it **CACHED REAL FEED**.

## 2. Live acquisition flow

```mermaid
sequenceDiagram
    participant UI as Dashboard
    participant API as FastAPI
    participant STAC as Planetary Computer STAC
    participant Geo as Nominatim
    participant Store as Neo4j/CSV cache

    UI->>API: GET /api/live-detect
    API->>STAC: POST scene search (Pune bbox, cloud < 20%)
    STAC-->>API: Scene metadata
    loop Up to 8 newest scenes
        API->>STAC: Sign and window-read B02/B03/B04/B08/B11/SCL COGs
        STAC-->>API: Signed asset URL
        STAC-->>API: Raster windows on a common 10 m UTM grid
    end
    API->>API: Compute NDVI/BSI, mask SCL classes, align, classify
    loop Findings
        API->>Geo: Reverse geocode coordinates
        Geo-->>API: Area name or fallback
    end
    API->>Store: Persist graph (CSV fallback) and display cache
    API-->>UI: JSON findings, timeline, media URLs
```

## 3. Image analysis flow

```mermaid
flowchart TD
    A[Historical/recent Sentinel-2 COG bands] --> B[NDVI and BSI]
    B --> C[Mask invalid/cloud/shadow pixels with SCL]
    C --> D[Align scenes and compare spectral changes]
    D --> E[NDVI loss or BSI gain threshold]
    E --> F[Connected components]
    F --> G[Area and georeferenced coordinates]
    G --> H[Optional ChangeCNN score]
    H --> I[Severity, confidence, error, links]
```

## 4. Finding review flow

Each finding contains:

- a human-readable area name when reverse geocoding succeeds;
- latitude/longitude;
- estimated changed area in square metres and hectares;
- an estimated error area;
- severity and confidence;
- a region bounding box;
- first and last observed dates;
- Google Maps and satellite URLs;
- a case-file status of `Needs review`.

Selecting a finding updates the case-file panel. The report button creates a
downloadable JSON report containing the source, observation window, finding,
and interpretation warning.

## 5. Timeline flow

The backend retains up to eight scenes. The oldest retained scene is the
baseline. Each adjacent scene pair is analyzed and contributes one timeline
point. Dates are scene acquisition dates, not fabricated monthly buckets.
Cloud filtering can create gaps longer than five days.

## 6. Upload flow

The dashboard can send two same-size image files to `POST /api/detect`.
Uploads do not use live catalog acquisition, but successful results use the
same Neo4j persistence with CSV fallback. Invalid images, mismatched
dimensions, and images over four megapixels return explicit errors.

## 7. Scheduled scan behavior

The browser schedules another request every ten minutes while the dashboard is
open. This is intentionally separate from satellite revisit timing:

- **Ten minutes:** dashboard refresh/polling.
- **Approximately five days:** Sentinel-2 revisit opportunity.
- **Up to eight scenes:** historical context returned by one live request.

Keep the dashboard open for automatic polling. A server-side scheduler is not
currently configured.

