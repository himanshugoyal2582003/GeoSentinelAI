# Global ML ready mining footprint dataset

This directory holds the public label/metadata archive for the Global ML ready
dataset for mining areas in satellite images (Jasansky et al., 2024). It covers
1,210 sites and 1,514 tile records, with train/validation/test splits for the
1,207 selected tiles.
The archive does not contain Sentinel-2 image pixels; the upstream workflow
retrieves matching Sentinel-2 L2A imagery from Microsoft's Planetary Computer.

Source: <https://doi.org/10.5281/zenodo.14195737>

The data is licensed CC BY-SA 4.0. Preserve attribution and the license terms
when redistributing adapted data. Sentinel-2 pixels remain subject to the
Copernicus data terms. See the [dataset record](https://zenodo.org/records/14195737)
for the full source details and attribution.

## Download and prepare image and mask tiles

Download and extract the metadata/mask archive if it is not already present:

```powershell
$projectRoot = (Get-Location).Path
$archive = Join-Path $projectRoot "dataset\public-global-mining\mining_area_data.zip"
if (-not (Test-Path $archive)) {
  Invoke-WebRequest "https://zenodo.org/api/records/14195737/files/mining_area_data.zip/content" -OutFile $archive
}
Expand-Archive -Path $archive -DestinationPath (Split-Path $archive) -Force
```

The repository includes a downloader that reads the provided tile splits and
preferred masks, fetches Sentinel-2 RGB bands from Microsoft's Planetary
Computer, and writes the image/mask pairs in the format expected by the
trainer. Run it from the repository root with the backend environment:

```powershell
backend\.venv\Scripts\python.exe scripts\download_public_mining_tiles.py
```

This creates `train`, `val`, and `test` subfolders under
`backend/data/public_mining`, each with matching `*_img.tif` and `*_mask.tif`
files. The downloader resumes completed tiles when rerun, records any failures
in `download_errors.json`, and can be limited for a small initial download with
`--limit N`. The masks label mine footprint presence, not illegal activity or
temporal expansion. The image archive is not checked into Git; the default
download is about 30 GB of uncompressed RGB tiles.

## Train the project model

From the backend directory, run:

```powershell
python train_mining_model.py
```

The trainer uses the dataset's provided train/validation/test splits and writes
`backend/models/mine_footprint_cnn.pt` and
`backend/models/mine_footprint_metrics.json`. The API exposes the probability
for changed patches when this model artifact is present. It does not replace
the existing weakly supervised change model.
