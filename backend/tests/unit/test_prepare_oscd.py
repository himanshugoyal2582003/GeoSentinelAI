from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_origin

from app.model_config import MODEL_BANDS, MODEL_INPUT_CHANNELS
from prepare_oscd import _read_change_mask, extract_patches, prepare_dataset


def _write_scene_city(images_root: Path, labels_root: Path, city_name: str) -> None:
    city_dir = images_root / city_name
    label_dir = labels_root / city_name / "cm"
    for date_dir in ("imgs_1_rect", "imgs_2_rect"):
        band_dir = city_dir / date_dir
        band_dir.mkdir(parents=True)
        for index, band_name in enumerate(MODEL_BANDS, start=1):
            with rasterio.open(
                band_dir / f"{band_name}.tif",
                "w",
                driver="GTiff",
                width=64,
                height=32,
                count=1,
                dtype="uint16",
                crs="EPSG:32643",
                transform=from_origin(400000, 2100000, 10, 10),
            ) as dataset:
                dataset.write(np.full((32, 64), index * 1000, dtype=np.uint16), 1)

    label_dir.mkdir(parents=True)
    mask = np.zeros((32, 64), dtype=np.uint8)
    mask[:, 32:] = 255
    Image.fromarray(mask).save(label_dir / "cm.png")


def test_extract_patches_keeps_ordered_ten_channels_and_binary_labels() -> None:
    historical = np.full((5, 32, 64), 0.1, dtype=np.float32)
    recent = np.full_like(historical, 0.2)
    mask = np.zeros((32, 64), dtype=bool)
    mask[:, 32:] = True

    features, labels = extract_patches(historical, recent, mask, patch_size=32, stride=32)

    assert features.shape == (2, MODEL_INPUT_CHANNELS, 32, 32)
    assert labels.tolist() == [0, 1]
    np.testing.assert_allclose(features[0, :5, 0, 0], [0.1] * 5)
    np.testing.assert_allclose(features[0, 5:, 0, 0], [0.2] * 5)


def test_prepare_dataset_uses_only_official_train_cities_and_reads_separate_masks(tmp_path: Path) -> None:
    images_root = tmp_path / "images"
    labels_root = tmp_path / "train-labels"
    images_root.mkdir()
    labels_root.mkdir()
    city_names = [f"city-{index}" for index in range(5)]
    (images_root / "train.txt").write_text(",".join(city_names), encoding="utf-8")
    (images_root / "test.txt").write_text("held-out-test-city", encoding="utf-8")
    for city_name in city_names:
        _write_scene_city(images_root, labels_root, city_name)

    output_root = tmp_path / "prepared"
    manifest = prepare_dataset(images_root, labels_root, output_root)

    assert manifest["inputChannels"] == MODEL_INPUT_CHANNELS
    assert manifest["officialTestCitiesUsed"] is False
    assert len(manifest["validationCities"]) == 1
    assert set(manifest["trainingCities"]).isdisjoint(manifest["validationCities"])
    assert set(manifest["trainingCities"] + manifest["validationCities"]) == set(city_names)
    assert len(manifest["splits"]["train"]) == 4
    assert len(manifest["splits"]["validation"]) == 1
    validation_city = manifest["validationCities"][0]
    validation_features = np.load(
        output_root / "validation" / validation_city / "features.npy",
        mmap_mode="r",
        allow_pickle=False,
    )
    validation_labels = np.load(
        output_root / "validation" / validation_city / "labels.npy",
        mmap_mode="r",
        allow_pickle=False,
    )
    assert validation_features.shape == (2, MODEL_INPUT_CHANNELS, 32, 32)
    assert validation_labels.tolist() == [0, 1]
    assert json.loads((output_root / "manifest.json").read_text(encoding="utf-8")) == manifest


def test_official_tiff_mask_uses_class_two_as_change(tmp_path: Path) -> None:
    mask_path = tmp_path / "city-cm.tif"
    mask = np.array([[1, 2], [1, 2]], dtype=np.uint8)
    with rasterio.open(
        mask_path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(0, 2, 1, 1),
    ) as dataset:
        dataset.write(mask, 1)
    with rasterio.open(mask_path) as reference:
        actual = _read_change_mask(mask_path, reference)

    assert actual.tolist() == [[False, True], [False, True]]
