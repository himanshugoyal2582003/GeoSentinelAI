from __future__ import annotations

import json
import csv
import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from app.change_model import ChangeCNN

ROOT = Path(__file__).resolve().parent
DATASET = ROOT.parent / "dataset" / "public-sentinel2-pune"
LABEL_FILE = DATASET / "labels.csv"
MODEL_DIR = ROOT / "models"
PATCH_SIZE = 32
SEED = 42


def load_pair() -> tuple[np.ndarray, np.ndarray]:
    historical = np.asarray(Image.open(DATASET / "historical.png").convert("RGB"), dtype=np.float32) / 255
    recent = np.asarray(Image.open(DATASET / "recent.png").convert("RGB"), dtype=np.float32) / 255
    return historical, recent


def patch(pair: tuple[np.ndarray, np.ndarray], x: int, y: int) -> np.ndarray:
    historical, recent = pair
    return np.concatenate(
        [historical[y : y + PATCH_SIZE, x : x + PATCH_SIZE], recent[y : y + PATCH_SIZE, x : x + PATCH_SIZE]],
        axis=2,
    ).transpose(2, 0, 1)


def create_samples(pair: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    random.seed(SEED)
    samples: list[np.ndarray] = []
    labels: list[float] = []
    height, width = pair[0].shape[:2]
    if LABEL_FILE.exists():
        with LABEL_FILE.open(newline="", encoding="utf-8") as handle:
            labeled = list(csv.DictReader(handle))
        for row in labeled:
            x, y = int(row["x"]), int(row["y"])
            samples.append(patch(pair, x, y))
            labels.append(float(row["label"]))
        if samples:
            return np.stack(samples).astype(np.float32), np.asarray(labels, dtype=np.float32)
    difference = np.mean(np.abs(pair[1] - pair[0]), axis=2)
    candidates: list[tuple[float, int, int]] = []
    for y in range(0, height - PATCH_SIZE, PATCH_SIZE):
        for x in range(0, width - PATCH_SIZE, PATCH_SIZE):
            candidates.append((float(difference[y : y + PATCH_SIZE, x : x + PATCH_SIZE].mean()), x, y))
    candidates.sort()
    negative_count = max(6, len(candidates) // 5)
    positive_count = max(6, len(candidates) // 5)
    for _, x, y in candidates[:negative_count]:
        samples.append(patch(pair, x, y))
        labels.append(0)
    for _, x, y in candidates[-positive_count:]:
        samples.append(patch(pair, x, y))
        labels.append(1)
    return np.stack(samples).astype(np.float32), np.asarray(labels, dtype=np.float32)


def main() -> None:
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    pair = load_pair()
    features, labels = create_samples(pair)
    indices = np.arange(len(labels))
    np.random.shuffle(indices)
    split = max(1, int(len(indices) * 0.8))
    train_indices, validation_indices = indices[:split], indices[split:]
    train = TensorDataset(torch.from_numpy(features[train_indices]), torch.from_numpy(labels[train_indices]))
    validation = TensorDataset(torch.from_numpy(features[validation_indices]), torch.from_numpy(labels[validation_indices]))

    model = ChangeCNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
    loss_fn = nn.BCEWithLogitsLoss()
    loader = DataLoader(train, batch_size=4, shuffle=True)
    for _ in range(40):
        model.train()
        for batch, target in loader:
            optimizer.zero_grad()
            loss = loss_fn(model(batch), target)
            loss.backward()
            optimizer.step()

    model.eval()
    with torch.no_grad():
        predictions = torch.sigmoid(model(torch.from_numpy(features[validation_indices])))
    predicted_labels = (predictions >= 0.5).float().numpy()
    validation_labels = labels[validation_indices]
    accuracy = float((predicted_labels == validation_labels).mean()) if len(validation_labels) else 0
    MODEL_DIR.mkdir(exist_ok=True)
    torch.save(model.state_dict(), MODEL_DIR / "change_cnn.pt")
    metrics = {
        "model": "ChangeCNN",
        "seed": SEED,
        "patchSize": PATCH_SIZE,
        "channels": 6,
        "trainSamples": len(train_indices),
        "validationSamples": len(validation_indices),
        "validationAccuracy": round(accuracy, 3),
        "dataset": str(DATASET),
        "labeling": "labels.csv expert labels when populated; otherwise measured top/bottom image-difference tiles.",
        "warning": "This is a real Sentinel-2 pair but weakly supervised; it is not a validated illegal-mining model.",
    }
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
