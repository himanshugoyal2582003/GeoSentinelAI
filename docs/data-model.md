# Data Model and Storage

## Runtime result

The live result is a JSON object composed of:

```text
result
├── scanId
├── region
├── historicalDate / recentDate
├── findings[]
├── summary
├── timeline[]
├── areaBreakdown[]
├── timelineNote
├── processing
└── source
```

## Finding

A finding is a connected changed component from one image pair. Its area is:

```text
areaSqm = changed_pixel_count × pixel_size_m × pixel_size_m
```

For live Sentinel-2 analysis, coordinates and bounding boxes are derived from
the 10 m UTM raster transform and converted to WGS-84. Uploaded image-pair
coordinates are estimated from the configured region and image pixels. Both
are suitable for review and map navigation, not survey-grade measurement.

## CSV scan history

Neo4j is the primary store for successful scan and finding observations.
`backend/data/scans.csv` is the fallback and stores:

- scan ID and UTC creation time;
- region and primary observation dates;
- historical/recent scene IDs;
- recent cloud cover;
- changed area;
- finding count;
- model name;
- processing metadata JSON.

## CSV finding history

`backend/data/findings.csv` is the corresponding finding fallback and stores:

- scan and finding IDs;
- reverse-geocoded area name;
- coordinates and area;
- severity and confidence;
- observation dates;
- region bounding box JSON.

## Dataset files

`dataset/public-sentinel2-pune/` contains:

- `historical.png` and `recent.png`: contrast-stretched RGB display previews
  downloaded from Sentinel-2 rendered-preview assets in the public STAC
  catalog;
- `manifest.json`: scene IDs, dates, cloud cover, source, and bbox;
- `labels.csv`: optional expert patch labels.

Live analysis reads the B02, B03, B04, B08, B11, and SCL COG assets directly.
The saved PNGs are for display only and are not used as analysis inputs.

## Cache and durability

`backend/data/live/` contains the latest two images and `last-result.json`.
Automatic static-region requests share a successful result for up to 30
minutes. Cached responses set `source.stale` and report `source.cacheAgeSeconds`;
an older cached result may be displayed after acquisition failure or during
the retry cooldown. Explicit `POST /api/live-detect` requests bypass the
shared cache. Render's default filesystem is ephemeral; CSV history and cache
should be moved to a persistent disk or external database for production
retention.

## Neo4j Graph Model

GeoSentinel persists findings and investigations in a Neo4j AuraDB graph
database. The CSV files remain as a backup/audit trail; Neo4j is the primary
queryable store.

### Node types (7)

| Label | Key property | Description |
|---|---|---|
| `MonitoringRegion` | `region_id` | A named geographic area that is scanned. Stores `name`, `bbox`, optional `geometry_geojson`, `is_monitoring_site`, `active`, and `created_at`. |
| `Scan` | `scan_id` | One complete satellite acquisition and analysis run. Stores `created_at`, `mode` (`live`/`upload`), `region_id`, `historical_date`, `recent_date`, `changed_area_sqm`, `finding_count`, `model_name`, `processing_metadata` (JSON string), `summary` (JSON string), `source_metadata` (JSON string), `status`, `idempotency_key` (optional). |
| `SatelliteScene` | `scene_id` | A single acquired satellite scene (Sentinel-2). Stores `provider`, `acquired_at`, `cloud_cover` (float, optional), `asset_metadata` (JSON string), `created_at`. |
| `FindingObservation` | `detection_id` | A detected change component from one scan. Stores `original_finding_id`, `scan_id`, `label`, `severity` (`high`/`medium`/`low`), `confidence` (0–1), `area_sqm`, `location` (spatial Point, see below), `first_observed`, `last_observed`, `change_type`, `model_score` (optional), `detection_error_sqm`, `region_bbox` (JSON string), `review_status`, `created_at`. |
| `EvidenceAsset` | `asset_id` | Metadata record for a saved evidence file (image, report). Stores `uri`, `sha256`, `media_type`, `file_size` (bytes), `asset_type`, `created_at`. **Image bytes are NOT stored in Neo4j**; `uri` points to external or local file storage. |
| `InvestigationCase` | `case_id` | A human-managed review case. Stores `title`, `status`, `review_status`, `created_at`, `updated_at`, `description`. |
| `Notification` | `notification_id` | Idempotent scheduled-alert queue item. Stores `scan_id`, `subject`, `body`, `status`, `attempts`, `created_at`, and delivery timestamps/errors. The operator recipient is read from deployment configuration, not stored in Neo4j. |

### Relationships (5)

| Relationship | Direction | Meaning |
|---|---|---|
| `(:MonitoringRegion)-[:HAS_SCAN]->(:Scan)` | Region → Scan | Links a scan to the region it monitored. |
| `(:Scan)-[:DETECTED]->(:FindingObservation)` | Scan → Finding | Links each detected component to its originating scan. |
| `(:Scan)-[:USED_SCENE]->(:SatelliteScene)` | Scan → Scene | Records which satellite scenes were used in the scan. |
| `(:FindingObservation)-[:HAS_EVIDENCE]->(:EvidenceAsset)` | Finding → Asset | Links evidence files (images, reports) to a finding. |
| `(:InvestigationCase)-[:INVESTIGATES]->(:FindingObservation)` | Case → Finding | Associates an investigation case with one or more findings. |

Custom monitoring sites are `MonitoringRegion` nodes with
`is_monitoring_site=true`. Their WGS-84 GeoJSON polygon is stored as a JSON
string; scans retain the site boundary in `source_metadata`. Deleting a site
sets `active=false` and preserves its graph and scan history.

### Spatial points (WGS-84)

`FindingObservation.location` is stored as a Neo4j `point` using WGS-84
coordinates. Live scan coordinates are derived from the native raster grid;
uploaded-image coordinates are estimated from the configured region:

```cypher
point({longitude: <lon>, latitude: <lat>, srid: 4326})
```

Neo4j uses `longitude` as the X axis and `latitude` as the Y axis. Coordinates
come from the centroid of the detected changed-pixel bounding box. They are
estimates suitable for map display, not survey-grade measurements.

A spatial index on `FindingObservation.location` supports `point.distance()`
proximity queries.

### Evidence asset storage note

Evidence asset files (PNG images, JSON reports) are **not** stored inside
Neo4j. The `EvidenceAsset` node contains metadata only: `uri`, `sha256`,
`media_type`, `file_size`, and `asset_type`. In local development files are
written under `backend/data/evidence/`. Production uses a private Cloudflare
R2 bucket through the S3-compatible evidence storage adapter. Scan-level
`source_metadata` records the before/after object URIs, hashes, and sizes;
Neo4j never stores the image bytes.

### Idempotency and MERGE strategy

All writes use Cypher `MERGE` on the unique key property so that retrying a
failed request does not create duplicate nodes:

```cypher
MERGE (s:Scan {scan_id: $scan_id})
ON CREATE SET s += $props
ON MATCH SET s.updated_at = $now
```

`Scan.idempotency_key` (optional) allows callers to supply their own
deduplication key. The schema enforces a `UNIQUE` constraint on this property
when present. All constraints and indexes are created by
`python scripts/init_neo4j_schema.py` and are idempotent (`CREATE CONSTRAINT IF
NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`).

