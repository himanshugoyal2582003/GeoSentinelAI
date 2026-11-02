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

Coordinates are estimated by mapping preview pixels into the static bounding
box. They are suitable for review and map navigation, not survey-grade
measurement.

## CSV scan history

`backend/data/scans.csv` stores:

- scan ID and UTC creation time;
- region and primary observation dates;
- historical/recent scene IDs;
- recent cloud cover;
- changed area;
- finding count;
- model name;
- processing metadata JSON.

## CSV finding history

`backend/data/findings.csv` stores:

- scan and finding IDs;
- reverse-geocoded area name;
- coordinates and area;
- severity and confidence;
- observation dates;
- region bounding box JSON.

## Dataset files

`dataset/public-sentinel2-pune/` contains:

- `historical.png` and `recent.png`: real rendered Sentinel-2 previews;
- `manifest.json`: scene IDs, dates, cloud cover, source, and bbox;
- `labels.csv`: optional expert patch labels.

The preview images are not analysis-ready multispectral GeoTIFF bands.

## Cache and durability

`backend/data/live/` contains the latest two images and `last-result.json`.
The cache allows graceful display after provider rate limiting. Render's
default filesystem is ephemeral; CSV history and cache should be moved to a
persistent disk or external database for production retention.

