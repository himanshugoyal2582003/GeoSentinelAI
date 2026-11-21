# GeoSentinel AI Documentation

GeoSentinel AI monitors the Pune quarry-belt bounding box for surface changes
between public Sentinel-2 observations. It is an intelligence and review tool,
not a legal determination or a replacement for field verification.

## Documentation map

- [System architecture](./system-architecture.md) — components, boundaries,
  dependencies, and deployment topology.
- [Working flow](./working-flow.md) — end-to-end scan, detection, review, and
  report workflow.
- [API reference](./api-reference.md) — endpoints, request parameters, and
  response contracts.
- [Data model](./data-model.md) — image, finding, scan, timeline, and CSV
  structures.
- [Operations guide](./operations.md) — local startup, Render deployment,
  CORS, scheduled scans, rate limits, and troubleshooting.
- [Pricing and free audit](./pricing-and-audit.md) — published plan, service
  limits, audit request form, and Netlify Forms setup.
- [Labeling and training](./labeling-and-training.md) — expert labels,
  retraining, metrics, and model limitations.

## Quick links

- Backend entry point: [`backend/app/main.py`](../backend/app/main.py)
- Frontend entry point: [`frontend/app/page.tsx`](../frontend/app/page.tsx)
- Render Blueprint: [`render.yaml`](../render.yaml)
- Dataset manifest:
  [`dataset/public-sentinel2-pune/manifest.json`](../dataset/public-sentinel2-pune/manifest.json)

## System scope

The current implementation uses:

1. A fixed Pune bounding box by default: `73.82–73.90` longitude and
   `18.48–18.56` latitude; user-defined polygons are also supported.
2. Microsoft Planetary Computer's public Sentinel-2 L2A STAC catalog.
3. Up to eight newest scenes with catalog cloud cover below 20%.
4. Native B02, B03, B04, B08, B11, and SCL COG windows resampled to a common
   10 m UTM grid; RGB previews are retained only for dashboard display.
5. Cloud-brightness masking, seasonal percentile normalization, FFT alignment,
   pixel differencing, connected components, and an optional six-channel CNN.
6. Neo4j as the primary scan/finding store, CSV as a recovery fallback, and
   Cloudflare R2 for durable scan previews when configured.

