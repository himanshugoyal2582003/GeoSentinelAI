from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
import torch
from rasterio.windows import Window
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from app.mining_model import MineFootprintCNN

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "data" / "public_mining"
MODEL_DIR = ROOT / "models"
PATCH_SIZE = 32
SEED = 42


def _normalize_rgb(image: np.ndarray) -> np.ndarray:
    """Match the per-channel 2nd/98th percentile stretch used by rgb_preview."""
    normalized = np.zeros(image.shape, dtype=np.float32)
    for channel in range(3):
        values = image[channel]
        valid = np.isfinite(values) & (values > 0)
        if not valid.any():
            continue
        low, high = np.percentile(values[valid], [2, 98])
        if high <= low:
            high = low + 1
        normalized[channel] = np.nan_to_num(np.clip((values - low) / (high - low), 0, 1))
    return normalized


def _sample_split(data_dir: Path, split: str, samples_per_class_per_tile: int) -> tuple[np.ndarray, np.ndarray]:
    split_dir = data_dir / split
    if not split_dir.is_dir():
        raise FileNotFoundError(f"Missing {split_dir}. Prepare the public mining dataset first.")

    images: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    image_paths = sorted(split_dir.glob("*_img.tif"))
    if not image_paths:
        raise FileNotFoundError(f"No *_img.tif tiles found in {split_dir}.")

    rng = np.random.default_rng(SEED + sum(map(ord, split)))
    for image_path in image_paths:
        mask_path = image_path.with_name(image_path.name.replace("_img.tif", "_mask.tif"))
        if not mask_path.exists():
            raise FileNotFoundError(f"Missing mask paired with {image_path.name}: {mask_path.name}")

        with rasterio.open(image_path) as image_source, rasterio.open(mask_path) as mask_source:
            if image_source.count < 3 or mask_source.count != 1:
                raise ValueError(f"Expected a 3-band image and 1-band mask for {image_path.name}.")
            if (image_source.width, image_source.height) != (mask_source.width, mask_source.height):
                raise ValueError(f"Image and mask dimensions differ for {image_path.name}.")
            rows = (image_source.height // PATCH_SIZE) * PATCH_SIZE
            cols = (image_source.width // PATCH_SIZE) * PATCH_SIZE
            if rows == 0 or cols == 0:
                continue

            mask = mask_source.read(1, window=Window(0, 0, cols, rows)) > 0
            rgb = _normalize_rgb(image_source.read([1, 2, 3]).astype(np.float32))
            block_mask = mask.reshape(
                rows // PATCH_SIZE, PATCH_SIZE, cols // PATCH_SIZE, PATCH_SIZE
            ).any(axis=(1, 3))
            positive_positions = np.argwhere(block_mask)
            negative_positions = np.argwhere(~block_mask)
            if not len(positive_positions) or not len(negative_positions):
                continue

            for positions in (positive_positions, negative_positions):
                count = min(samples_per_class_per_tile, len(positions))
                chosen = positions[rng.choice(len(positions), size=count, replace=False)]
                for block_y, block_x in chosen:
                    y, x = int(block_y * PATCH_SIZE), int(block_x * PATCH_SIZE)
                    window = Window(x, y, PATCH_SIZE, PATCH_SIZE)
                    image = rgb[:, y : y + PATCH_SIZE, x : x + PATCH_SIZE]
                    label = mask[y : y + PATCH_SIZE, x : x + PATCH_SIZE].astype(np.float32)
                    if not np.isfinite(image).any() or np.all(image == 0):
                        continue
                    images.append(image.copy())
                    masks.append(label)

    if not images:
        raise ValueError(f"No usable labeled patches found in {split_dir}.")
    return np.stack(images), np.stack(masks)


def _metrics(model: MineFootprintCNN, features: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    model.eval()
    intersection = union = true_positive = false_positive = false_negative = 0
    loader = DataLoader(TensorDataset(torch.from_numpy(features), torch.from_numpy(labels)), batch_size=32)
    with torch.no_grad():
        for batch, target in loader:
            predicted = torch.sigmoid(model(batch)) >= 0.5
            expected = target >= 0.5
            intersection += (predicted & expected).sum().item()
            union += (predicted | expected).sum().item()
            true_positive += (predicted & expected).sum().item()
            false_positive += (predicted & ~expected).sum().item()
            false_negative += (~predicted & expected).sum().item()
    return {
        "iou": round(intersection / union, 4) if union else 1.0,
        "precision": round(true_positive / (true_positive + false_positive), 4)
        if true_positive + false_positive else 0.0,
        "recall": round(true_positive / (true_positive + false_negative), 4)
        if true_positive + false_negative else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a mine-footprint segmenter on the public Sentinel-2 masks.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--samples-per-class-per-tile", type=int, default=4)
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1 or args.samples_per_class_per_tile < 1:
        parser.error("epochs, batch-size, and samples-per-class-per-tile must be positive")

    torch.manual_seed(SEED)
    np.random.seed(SEED)
    train_features, train_labels = _sample_split(
        args.data_dir, "train", args.samples_per_class_per_tile
    )
    validation_features, validation_labels = _sample_split(
        args.data_dir, "val", args.samples_per_class_per_tile
    )
    test_features, test_labels = _sample_split(
        args.data_dir, "test", args.samples_per_class_per_tile
    )

    train = TensorDataset(torch.from_numpy(train_features), torch.from_numpy(train_labels))
    loader = DataLoader(train, batch_size=args.batch_size, shuffle=True)
    model = MineFootprintCNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    positive_pixels = float(train_labels.sum())
    total_pixels = float(train_labels.size)
    positive_weight = min(100.0, max(1.0, (total_pixels - positive_pixels) / max(positive_pixels, 1.0)))
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(positive_weight))

    for _ in range(args.epochs):
        model.train()
        for batch, target in loader:
            optimizer.zero_grad()
            logits = model(batch)
            bce = loss_fn(logits, target)
            probabilities = torch.sigmoid(logits)
            dice = 1 - (2 * (probabilities * target).sum() + 1) / (probabilities.sum() + target.sum() + 1)
            loss = bce + dice
            loss.backward()
            optimizer.step()

    validation_metrics = _metrics(model, validation_features, validation_labels)
    test_metrics = _metrics(model, test_features, test_labels)
    MODEL_DIR.mkdir(exist_ok=True)
    torch.save(model.state_dict(), MODEL_DIR / "mine_footprint_cnn.pt")
    metrics = {
        "model": "MineFootprintCNN",
        "task": "Sentinel-2 mine footprint segmentation",
        "source": "Jasansky et al. (2024), Global ML-ready dataset for mining areas in satellite images",
        "sourceDoi": "10.5281/zenodo.14195737",
        "sourceLicense": "CC BY-SA 4.0; retain attribution and share-alike terms for adapted dataset material.",
        "seed": SEED,
        "patchSize": PATCH_SIZE,
        "channels": 3,
        "trainPatches": len(train_features),
        "validationPatches": len(validation_features),
        "testPatches": len(test_features),
        "positiveWeight": round(positive_weight, 3),
        "validation": validation_metrics,
        "test": test_metrics,
        "warning": "Mine footprint labels do not establish illegal activity or temporal expansion.",
    }
    (MODEL_DIR / "mine_footprint_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
