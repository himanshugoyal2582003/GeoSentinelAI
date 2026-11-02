# Public Sentinel-2 comparison dataset

This folder contains a compact, public Sentinel-2 image pair for the Pune quarry-belt demo:

- `historical.png`: 2025-10-20 scene preview
- `recent.png`: 2026-10-25 scene preview
- `manifest.json`: scene IDs, dates, cloud cover, source, and bounding box

The images were collected from the Microsoft Planetary Computer STAC catalog, using Copernicus Sentinel-2 L2A rendered previews. They are real public imagery, but the previews are not a substitute for analysis-ready 10 m GeoTIFF bands.

Run the comparison from the repository root:

```powershell
python dataset\compare_results.py
```

The backend trains on this real pair using weak labels generated from measured
image differences. These labels identify changed surface tiles, not confirmed
illegal activity.
