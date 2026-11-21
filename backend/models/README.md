# Model artifacts

This directory contains the checked-in `change_cnn.pt` checkpoint and
`metrics.json`. The legacy checkpoint is supported until OSCD data is
prepared and a compatible multispectral model is trained.

Training outputs are written here by `backend/train_model.py`. The training
data itself belongs under ignored `backend/data/oscd/`; it must not be
committed. See [`docs/labeling-and-training.md`](../../docs/labeling-and-training.md).
