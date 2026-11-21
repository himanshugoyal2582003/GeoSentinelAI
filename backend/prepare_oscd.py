from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import reproject

from app.model_config import MODEL_BANDS, MODEL_INPUT_CHANNELS

DEFAULT_IMAGE1_DIR = "imgs_1_rect"
DEFAULT_IMAGE2_DIR = "imgs_2_rect"
DEFAULT_PATCH_SIZE = 32
VALIDATION_SEED = 42


def _read_band(path: Path, target: rasterio.DatasetReader | None = None) -> np.ndarray:
    with rasterio.open(path) as dataset:
        band = dataset.read(1, masked=True).astype(np.float32).filled(np.nan)
        scale = dataset.scales[0] if dataset.scales else 1.0
        if scale is None or not np.isfinite(scale) or scale == 1:
            dtype = np.dtype(dataset.dtypes[0])
            scale = 0.0001 if np.issubdtype(dtype, np.integer) else 1.0
        band *= scale

        needs_reprojection = target is not None and (
            band.shape != (target.height, target.width)
            or (
                dataset.crs is not None
                and target.crs is not None
                and (dataset.crs != target.crs or dataset.transform != target.transform)
            )
        )
        if needs_reprojection:
            if dataset.crs is None or target.crs is None:
                raise ValueError(
                    f"{path} does not match the reference grid and cannot be reprojected."
                )
            aligned = np.full((target.height, target.width), np.nan, dtype=np.float32)
            reproject(
                source=band,
                destination=aligned,
                src_transform=dataset.transform,
                src_crs=dataset.crs,
                src_nodata=np.nan,
                dst_transform=target.transform,
                dst_crs=target.crs,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
            )
            band = aligned
    return np.clip(band, 0, 1).astype(np.float32)


def _read_reflectance(directory: Path, target: rasterio.DatasetReader | None = None) -> np.ndarray:
    if not directory.is_dir():
        raise FileNotFoundError(f"Expected OSCD per-band directory: {directory}")
    reference_path = directory / f"{MODEL_BANDS[0]}.tif"
    if not reference_path.is_file():
        raise FileNotFoundError(f"Missing OSCD band file: {reference_path}")

    with rasterio.open(reference_path) as reference:
        bands = []
        for band_name in MODEL_BANDS:
            band_path = directory / f"{band_name}.tif"
            if not band_path.is_file():
                raise FileNotFoundError(f"Missing OSCD band file: {band_path}")
            bands.append(_read_band(band_path, target=target if target is not None else reference))
    return np.stack(bands).astype(np.float32)


def _read_change_mask(path: Path, reference: rasterio.DatasetReader) -> np.ndarray:
    if path.suffix.lower() in {".tif", ".tiff"}:
        with rasterio.open(path) as dataset:
            mask = dataset.read(1, masked=True).astype(np.float32).filled(0)
            same_shape = mask.shape == (reference.height, reference.width)
            same_grid = (
                dataset.crs is not None
                and reference.crs is not None
                and dataset.crs == reference.crs
                and dataset.transform == reference.transform
            )
            if same_shape and (same_grid or (dataset.crs is None and reference.crs is None)):
                return (mask == 2) if np.any(mask == 2) else (mask > 0)
            if dataset.crs is None or reference.crs is None:
                if same_shape:
                    return (mask == 2) if np.any(mask == 2) else (mask > 0)
                raise ValueError(f"Unreferenced mask {path} must match the reference image dimensions.")
            aligned = np.zeros((reference.height, reference.width), dtype=np.float32)
            reproject(
                source=mask,
                destination=aligned,
                src_transform=dataset.transform,
                src_crs=dataset.crs,
                src_nodata=dataset.nodata,
                dst_transform=reference.transform,
                dst_crs=reference.crs,
                dst_nodata=0,
                resampling=Resampling.nearest,
            )
            return (aligned == 2) if np.any(aligned == 2) else (aligned > 0)

    with Image.open(path) as image:
        mask = np.asarray(image.convert("L"))
    if mask.shape != (reference.height, reference.width):
        raise ValueError(
            f"Mask {path} dimensions {mask.shape[::-1]} do not match reference image "
            f"{(reference.width, reference.height)}."
        )
    return mask > 0


def extract_patches(
    historical: np.ndarray,
    recent: np.ndarray,
    change_mask: np.ndarray,
    patch_size: int = DEFAULT_PATCH_SIZE,
    stride: int = DEFAULT_PATCH_SIZE,
    min_valid_fraction: float = 0.98,
    min_change_fraction: float = 0.01,
) -> tuple[np.ndarray, np.ndarray]:
    if historical.shape != recent.shape or historical.ndim != 3:
        raise ValueError("Historical and recent scenes must share a bands-by-height-by-width shape.")
    if change_mask.shape != historical.shape[1:]:
        raise ValueError("Change mask dimensions must match the scene pair.")
    if patch_size < 1 or stride < 1:
        raise ValueError("Patch size and stride must be positive.")
    if not 0 < min_valid_fraction <= 1 or not 0 <= min_change_fraction <= 1:
        raise ValueError("Patch valid/change fractions must be between zero and one.")

    valid = np.all(np.isfinite(historical) & np.isfinite(recent), axis=0)
    height, width = change_mask.shape
    patches: list[np.ndarray] = []
    labels: list[int] = []
    for y in range(0, height - patch_size + 1, stride):
        for x in range(0, width - patch_size + 1, stride):
            patch_valid = valid[y : y + patch_size, x : x + patch_size]
            valid_pixels = int(patch_valid.sum())
            if valid_pixels / (patch_size * patch_size) < min_valid_fraction:
                continue
            changed_pixels = int(
                np.count_nonzero(change_mask[y : y + patch_size, x : x + patch_size] & patch_valid)
            )
            fraction = changed_pixels / valid_pixels
            patch = np.concatenate(
                [
                    historical[:, y : y + patch_size, x : x + patch_size],
                    recent[:, y : y + patch_size, x : x + patch_size],
                ],
                axis=0,
            )
            patches.append(np.nan_to_num(patch, nan=0.0, posinf=0.0, neginf=0.0))
            labels.append(int(fraction >= min_change_fraction))

    if not patches:
        return (
            np.empty((0, MODEL_INPUT_CHANNELS, patch_size, patch_size), dtype=np.float32),
            np.empty((0,), dtype=np.uint8),
        )
    return np.stack(patches).astype(np.float32), np.asarray(labels, dtype=np.uint8)


def _find_mask(city_dir: Path, mask_name: str) -> Path:
    candidates = [
        city_dir / mask_name,
        city_dir / "cm" / mask_name,
        city_dir / "cm" / f"{city_dir.name}-cm.tif",
        city_dir / "cm.tif",
        city_dir / "cm.tiff",
        city_dir / "cm" / "cm.png",
        city_dir / "change_mask.tif",
        city_dir / "change_mask.png",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(f"No change mask found in {city_dir}; checked {', '.join(path.name for path in candidates)}.")


def _save_npy(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("wb") as handle:
        np.save(handle, values, allow_pickle=False)
    temporary_path.replace(path)


def prepare_city(
    city_dir: Path,
    label_city_dir: Path,
    output_dir: Path,
    *,
    image1_dir_name: str = DEFAULT_IMAGE1_DIR,
    image2_dir_name: str = DEFAULT_IMAGE2_DIR,
    mask_name: str = "cm.png",
    patch_size: int = DEFAULT_PATCH_SIZE,
    stride: int = DEFAULT_PATCH_SIZE,
    min_valid_fraction: float = 0.98,
    min_change_fraction: float = 0.01,
) -> dict[str, Any]:
    image1_path = city_dir / image1_dir_name
    image2_path = city_dir / image2_dir_name
    mask_path = _find_mask(label_city_dir, mask_name)

    with rasterio.open(image1_path / f"{MODEL_BANDS[0]}.tif") as reference:
        historical = _read_reflectance(image1_path)
        recent = _read_reflectance(image2_path, target=reference)
        change_mask = _read_change_mask(mask_path, reference)
    features, labels = extract_patches(
        historical,
        recent,
        change_mask,
        patch_size,
        stride,
        min_valid_fraction,
        min_change_fraction,
    )
    if len(labels) == 0:
        raise ValueError(f"No valid patches could be extracted from {city_dir}.")

    city_output = output_dir / city_dir.name
    _save_npy(city_output / "features.npy", features)
    _save_npy(city_output / "labels.npy", labels)
    return {
        "city": city_dir.name,
        "patches": int(len(labels)),
        "changedPatches": int(labels.sum()),
        "stablePatches": int(len(labels) - labels.sum()),
    }


def _split_city_dirs(dataset_root: Path, split: str) -> list[Path]:
    split_list = dataset_root / f"{split}.txt"
    if not split_list.is_file():
        raise FileNotFoundError(f"OSCD split list not found: {split_list}")
    city_names = [
        name.strip()
        for line in split_list.read_text(encoding="utf-8").splitlines()
        for name in line.split(",")
        if name.strip()
    ]
    cities = [dataset_root / name for name in city_names]
    if not cities or any(not city.is_dir() for city in cities):
        raise ValueError(f"OSCD split '{split}' contains no readable city directories.")
    return cities


def prepare_dataset(
    dataset_root: Path,
    labels_root: Path,
    output_root: Path,
    *,
    image1_dir_name: str = DEFAULT_IMAGE1_DIR,
    image2_dir_name: str = DEFAULT_IMAGE2_DIR,
    mask_name: str = "cm.png",
    patch_size: int = DEFAULT_PATCH_SIZE,
    stride: int = DEFAULT_PATCH_SIZE,
    min_valid_fraction: float = 0.98,
    min_change_fraction: float = 0.01,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "dataset": "OSCD",
        "bandsPerDate": list(MODEL_BANDS),
        "inputChannels": MODEL_INPUT_CHANNELS,
        "patchSize": patch_size,
        "stride": stride,
        "splits": {},
    }
    official_train_cities = _split_city_dirs(dataset_root, "train")
    if len(official_train_cities) < 2:
        raise ValueError("OSCD needs at least two official training cities for a city-level validation split.")
    validation_count = max(1, round(len(official_train_cities) * 0.2))
    validation_names = set(random.Random(VALIDATION_SEED).sample(
        [city.name for city in official_train_cities],
        validation_count,
    ))
    validation_cities = [city for city in official_train_cities if city.name in validation_names]
    training_cities = [city for city in official_train_cities if city.name not in validation_names]
    missing_label_cities = [
        city.name for city in official_train_cities if not (labels_root / city.name).is_dir()
    ]
    if missing_label_cities:
        example_city = missing_label_cities[0]
        raise FileNotFoundError(
            "OSCD Train Labels are missing city folders: "
            f"{', '.join(missing_label_cities)}. The labels directory must directly contain "
            f"city folders with masks, for example {labels_root / example_city / 'cm' / mask_name}. "
            "Extract the separate Train Labels archive and pass its city-folder root."
        )

    for output_split, city_dirs in (("train", training_cities), ("validation", validation_cities)):
        city_summaries = []
        for city_dir in city_dirs:
            label_city_dir = labels_root / city_dir.name
            city_summaries.append(
                prepare_city(
                    city_dir,
                    label_city_dir,
                    output_root / output_split,
                    image1_dir_name=image1_dir_name,
                    image2_dir_name=image2_dir_name,
                    mask_name=mask_name,
                    patch_size=patch_size,
                    stride=stride,
                    min_valid_fraction=min_valid_fraction,
                    min_change_fraction=min_change_fraction,
                )
            )
        summary["splits"][output_split] = city_summaries
    summary["officialTestCitiesUsed"] = False
    summary["validationSeed"] = VALIDATION_SEED
    summary["validationCities"] = [city.name for city in validation_cities]
    summary["trainingCities"] = [city.name for city in training_cities]

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare OSCD Sentinel-2 pairs as 10-channel training patches.")
    parser.add_argument("--source", type=Path, required=True, help="Extracted OSCD Images archive directory.")
    parser.add_argument("--labels", type=Path, required=True, help="Extracted OSCD Train Labels archive directory.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "oscd",
        help="Output directory for prepared patches (defaults to backend/data/oscd).",
    )
    parser.add_argument("--image1-dir-name", default=DEFAULT_IMAGE1_DIR)
    parser.add_argument("--image2-dir-name", default=DEFAULT_IMAGE2_DIR)
    parser.add_argument("--mask-name", default="cm.png")
    parser.add_argument("--patch-size", type=int, default=DEFAULT_PATCH_SIZE)
    parser.add_argument("--stride", type=int, default=DEFAULT_PATCH_SIZE)
    parser.add_argument("--min-valid-fraction", type=float, default=0.98)
    parser.add_argument("--min-change-fraction", type=float, default=0.01)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    summary = prepare_dataset(
        args.source,
        args.labels,
        args.output,
        image1_dir_name=args.image1_dir_name,
        image2_dir_name=args.image2_dir_name,
        mask_name=args.mask_name,
        patch_size=args.patch_size,
        stride=args.stride,
        min_valid_fraction=args.min_valid_fraction,
        min_change_fraction=args.min_change_fraction,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
