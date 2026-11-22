# Labeling and Training

## Label file

Add patch labels to
[`dataset/public-sentinel2-pune/labels.csv`](../dataset/public-sentinel2-pune/labels.csv):

```csv
x,y,label,source,notes
120,80,1,expert,Confirmed quarry expansion
250,160,0,expert,Stable land
```

- `x`, `y`: top-left patch coordinates in the dataset preview images.
- `label`: `1` for confirmed change and `0` for stable land.
- `source`: label provenance, normally `expert`.
- `notes`: evidence or review note.

The current trainer uses 32×32 patches. Labeled rows are used when present;
otherwise it creates weak labels from the lowest and highest measured
image-difference tiles.

## Training

```powershell
cd E:\hackfront\backend
python train_model.py
```

Outputs:

- `backend/models/change_cnn.pt`
- `backend/models/metrics.json`

The model has six input channels: historical RGB plus recent RGB. It is a
small CPU-oriented CNN. The API loads it at process startup and falls back to
image differencing if the artifact is missing or invalid.

## Interpreting metrics

The reported validation accuracy is only meaningful with enough independent,
expert-labeled scene pairs. A high score from weak labels is not evidence that
the system reliably detects illegal quarrying.

## Public mine footprint training

The repository also supports an independently trained mine footprint segmenter
using the Global ML ready dataset for mining areas. It covers 1,210 sites, but
its labels identify mining footprints; they do not establish illegal activity
or temporal expansion. The dataset record is at
<https://doi.org/10.5281/zenodo.14195737> and its labels are CC BY-SA 4.0.
The archive contains masks and metadata, not Sentinel-2 pixels. Follow
[`dataset/public-global-mining/README.md`](../dataset/public-global-mining/README.md)
to prepare imagery and masks with the dataset authors' workflow, then run
`python train_mining_model.py` from `backend`.

This produces a separate `mine_footprint_cnn.pt` artifact. Its validation and
test metrics use the source dataset's provided splits, and the API reports
its mine-footprint likelihood separately from the change model score.

For a stronger model, collect multiple dates and locations, label both changed
and unchanged patches, preserve cloud/season diversity, and keep a separate
expert-reviewed validation set.

