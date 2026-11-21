# Labeling and Training

## OSCD training data

Phase 3 uses the Onera Satellite Change Detection (OSCD) benchmark rather
than the RGB preview images in `dataset/public-sentinel2-pune`. Download and
extract the **Images** and **Train Labels** archives from the
[OSCD dataset page](https://ieee-dataport.org/open-access/oscd-onera-satellite-change-detection).
Keep these archives outside Git. The extracted directories should contain:

```text
Onera Satellite Change Detection dataset - Images/
  train.txt
  city-name/
    imgs_1_rect/B02.tif ... B11.tif
    imgs_2_rect/B02.tif ... B11.tif
Onera Satellite Change Detection dataset - Train Labels/
  city-name/cm/cm.png
```

Use the corresponding actual band files `B02`, `B03`, `B04`, `B08`, and
`B11` from each rectified date folder. Labels are in the separate Train
Labels archive. OSCD's held-out official test cities are not used in training
or validation; 20% of the official training cities are held out by city for
validation.

From `backend`, prepare patches and train:

```powershell
$images = Read-Host "Full path to the extracted OSCD Images directory"
$labels = Read-Host "Full path to the extracted OSCD Train Labels directory"
if (-not (Test-Path -LiteralPath (Join-Path $images "train.txt"))) {
  throw "The Images directory must contain train.txt: $images"
}
if (-not (Test-Path -LiteralPath $labels)) {
  throw "The Train Labels directory does not exist: $labels"
}
if (-not (Test-Path -LiteralPath (Join-Path $labels "bordeaux\cm\cm.png")) -and
    -not (Test-Path -LiteralPath (Join-Path $labels "bordeaux\cm\cm.tif"))) {
  throw "The Train Labels directory must directly contain city folders, including bordeaux\cm\cm.png or cm.tif."
}
.\.venv\Scripts\python.exe prepare_oscd.py --source $images --labels $labels
if ($LASTEXITCODE -ne 0) { throw "OSCD patch preparation failed." }
.\.venv\Scripts\python.exe train_model.py
```

Preparation writes 32×32, 10-channel paired patches and a manifest under
`backend/data/oscd/`. The directory is ignored by Git. Training uses
memory-mapped patch files and fails clearly if preparation, labels, or either
class is missing. Do not copy example paths from another computer; use the
actual directories created when you extracted both archives.

Training outputs:

- `backend/models/change_cnn.pt`
- `backend/models/metrics.json`

The model has ten input channels: B02, B03, B04, B08, and B11 for each date.
The API reloads the trained model after successful training. Until OSCD data
is supplied and training completes, the existing six-channel RGB checkpoint
remains supported. An RGB upload cannot be scored by a 10-channel checkpoint,
so that model score is skipped for uploads.

## Interpreting metrics

OSCD labels general land-cover change, not illegal quarry activity. Validation
metrics are for the OSCD change-detection task only and do not establish that
the system reliably detects illegal quarrying.

Quarry monitoring still needs independently collected, expert-reviewed quarry
labels and a separate evaluation set before making operational claims.

