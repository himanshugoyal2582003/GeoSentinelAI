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

1. A fixed Pune bounding box: `73.82–73.90` longitude and `18.48–18.56`
   latitude.
2. Microsoft Planetary Computer's public Sentinel-2 L2A STAC catalog.
3. Up to eight newest scenes with catalog cloud cover below 20%.
4. Rendered RGB preview assets rather than analysis-ready multispectral bands.
5. Cloud-brightness masking, seasonal percentile normalization, FFT alignment,
   pixel differencing, connected components, and an optional six-channel CNN.
6. CSV files for scan and finding history.

