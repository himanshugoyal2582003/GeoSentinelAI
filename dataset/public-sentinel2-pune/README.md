# Public Sentinel-2 comparison dataset

This folder contains a compact, public Sentinel-2 image pair for the Pune quarry-belt demo:

- `historical.png`: 2025-10-20 scene preview
- `recent.png`: 2026-10-15 scene preview
- `manifest.json`: scene IDs, dates, cloud cover, source, and bounding box

The images were collected from the Microsoft Planetary Computer STAC catalog, using Copernicus Sentinel-2 L2A rendered previews. They are real public imagery, but the previews are not a substitute for analysis-ready 10 m GeoTIFF bands.

`labels.csv` contains weak labels for changed surface tiles. These labels
describe image differences; they do not confirm quarry activity or illegal
behavior. The application uses this folder as a documented demo asset, while
live analysis reads native Sentinel-2 COG bands from the public catalog.

See the [dataset guide](../README.md) for asset details and the
[labeling and training guide](../../docs/labeling-and-training.md) for OSCD
training data instructions.
