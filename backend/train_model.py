from __future__ import annotations

import json
import random
from bisect import bisect_right
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from app.change_model import ChangeCNN
from app.model_config import MODEL_BANDS, MODEL_INPUT_CHANNELS

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "data" / "oscd"
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "change_cnn.pt"
METRICS_PATH = MODEL_DIR / "metrics.json"
SEED = 42
EPOCHS = 20
BATCH_SIZE = 64


class NpyPatchDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    """Memory-mapped patch dataset, keeping large OSCD arrays out of RAM."""

    def __init__(self, split_dir: Path) -> None:
        if not split_dir.is_dir():
            raise FileNotFoundError(f"Prepared split not found: {split_dir}")
        city_dirs = sorted(path for path in split_dir.iterdir() if path.is_dir())
        if not city_dirs:
            raise ValueError(f"No prepared city patches found in {split_dir}")

        self.features: list[np.ndarray] = []
        self.labels: list[np.ndarray] = []
        self.offsets = [0]
        for city_dir in city_dirs:
            feature_path = city_dir / "features.npy"
            label_path = city_dir / "labels.npy"
            if not feature_path.is_file() or not label_path.is_file():
                raise FileNotFoundError(f"Expected features.npy and labels.npy in {city_dir}")
            features = np.load(feature_path, mmap_mode="r", allow_pickle=False)
            labels = np.load(label_path, mmap_mode="r", allow_pickle=False)
            if (
                features.ndim != 4
                or features.shape[1] != MODEL_INPUT_CHANNELS
                or labels.shape != (features.shape[0],)
            ):
                raise ValueError(
                    f"Invalid prepared arrays in {city_dir}: expected N×{MODEL_INPUT_CHANNELS}×H×W "
                    "features and N labels."
                )
            if features.shape[0] == 0:
                continue
            self.features.append(features)
            self.labels.append(labels)
            self.offsets.append(self.offsets[-1] + features.shape[0])

        if not self.features:
            raise ValueError(f"No non-empty patch arrays found in {split_dir}")

    def __len__(self) -> int:
        return self.offsets[-1]

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        if index < 0 or index >= len(self):
            raise IndexError(index)
        city_index = bisect_right(self.offsets, index) - 1
        patch_index = index - self.offsets[city_index]
        features = np.array(self.features[city_index][patch_index], dtype=np.float32, copy=True)
        label = np.float32(self.labels[city_index][patch_index])
        return torch.from_numpy(features), torch.tensor(label, dtype=torch.float32)

    def class_counts(self) -> tuple[int, int]:
        positive = sum(int(np.count_nonzero(labels)) for labels in self.labels)
        return len(self) - positive, positive


def _evaluate(
    model: ChangeCNN,
    loader: DataLoader[tuple[torch.Tensor, torch.Tensor]],
) -> dict[str, float]:
    model.eval()
    predictions: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    with torch.no_grad():
        for batch, labels in loader:
            predictions.append(torch.sigmoid(model(batch)).cpu().numpy())
            targets.append(labels.cpu().numpy())
    predicted = np.concatenate(predictions) >= 0.5
    expected = np.concatenate(targets) >= 0.5
    true_positive = int(np.count_nonzero(predicted & expected))
    false_positive = int(np.count_nonzero(predicted & ~expected))
    false_negative = int(np.count_nonzero(~predicted & expected))
    accuracy = float(np.mean(predicted == expected))
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def train() -> dict[str, object]:
    train_dir = DATASET / "train"
    validation_dir = DATASET / "validation"
    if not train_dir.is_dir() or not validation_dir.is_dir():
        raise FileNotFoundError(
            "Prepared OSCD patches are missing. Run "
            "`python prepare_oscd.py --source <OSCD_IMAGES_DIR> --labels <OSCD_TRAIN_LABELS_DIR>` first."
        )

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    training = NpyPatchDataset(train_dir)
    validation = NpyPatchDataset(validation_dir)
    negative_count, positive_count = training.class_counts()
    if not positive_count or not negative_count:
        raise ValueError("OSCD training split must contain both changed and stable patches.")

    train_loader = DataLoader(training, batch_size=BATCH_SIZE, shuffle=True)
    validation_loader = DataLoader(validation, batch_size=BATCH_SIZE, shuffle=False)
    model = ChangeCNN()
    positive_weight = torch.tensor(min(20.0, negative_count / positive_count), dtype=torch.float32)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=positive_weight)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.0005)

    epoch_losses: list[float] = []
    for _ in range(EPOCHS):
        model.train()
        batch_losses = []
        for batch, labels in train_loader:
            optimizer.zero_grad()
            loss = loss_fn(model(batch), labels)
            loss.backward()
            optimizer.step()
            batch_losses.append(float(loss.detach()))
        epoch_losses.append(float(np.mean(batch_losses)))

    validation_metrics = _evaluate(model, validation_loader)
    metrics: dict[str, object] = {
        "model": "ChangeCNN",
        "architecture": "paired-sentinel2-10-channel",
        "seed": SEED,
        "patchSize": int(training.features[0].shape[-1]),
        "channels": MODEL_INPUT_CHANNELS,
        "bandsPerDate": list(MODEL_BANDS),
        "trainSamples": len(training),
        "validationSamples": len(validation),
        "trainStableSamples": negative_count,
        "trainChangedSamples": positive_count,
        "epochs": EPOCHS,
        "finalTrainingLoss": round(epoch_losses[-1], 6),
        "validation": validation_metrics,
        "validationAccuracy": validation_metrics["accuracy"],
        "dataset": "OSCD",
        "labeling": "Official OSCD binary change masks; city-level split from official training cities.",
        "warning": "OSCD labels represent land-cover change, not illegal quarry activity.",
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_tmp = MODEL_PATH.with_suffix(".pt.tmp")
    metrics_tmp = METRICS_PATH.with_suffix(".json.tmp")
    torch.save(model.state_dict(), model_tmp)
    model_tmp.replace(MODEL_PATH)
    metrics_tmp.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    metrics_tmp.replace(METRICS_PATH)
    return metrics


def main() -> None:
    metrics = train()
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
