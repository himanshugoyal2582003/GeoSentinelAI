from __future__ import annotations

import numpy as np
import pytest

from app.satellite_cog import create_target_grid, pixel_bounds_wgs84, pixel_center_wgs84
from app.spectral import calculate_indices, compare_spectral_scenes, scl_cloud_mask


def test_indices_are_computed_from_sentinel_bands() -> None:
    bands = {
        "B02": np.array([[0.1]], dtype=np.float32),
        "B04": np.array([[0.2]], dtype=np.float32),
        "B08": np.array([[0.6]], dtype=np.float32),
        "B11": np.array([[0.5]], dtype=np.float32),
    }

    ndvi, bsi = calculate_indices(bands)

    assert ndvi[0, 0] == pytest.approx(0.5)
    assert bsi[0, 0] == pytest.approx(0.0, abs=1e-6)


def test_scl_masks_cloud_and_unusable_classes() -> None:
    scl = np.arange(12, dtype=np.uint8).reshape(3, 4)

    mask = scl_cloud_mask(scl)

    assert np.flatnonzero(mask.ravel()).tolist() == [0, 1, 3, 7, 8, 9, 10, 11]
    assert not mask[1, 0]
    assert not mask[1, 2]


def test_spectral_change_detects_vegetation_loss_and_excludes_clouds() -> None:
    shape = (20, 20)
    old = {
        "B02": np.full(shape, 0.1, dtype=np.float32),
        "B03": np.full(shape, 0.2, dtype=np.float32),
        "B04": np.full(shape, 0.2, dtype=np.float32),
        "B08": np.full(shape, 0.6, dtype=np.float32),
        "B11": np.full(shape, 0.5, dtype=np.float32),
    }
    new = {name: values.copy() for name, values in old.items()}
    new["B04"][5:10, 5:10] = 0.6
    new["B08"][5:10, 5:10] = 0.2
    new["B04"][:5, :5] = 0.6
    new["B08"][:5, :5] = 0.2
    old_scl = np.full(shape, 5, dtype=np.uint8)
    new_scl = old_scl.copy()
    new_scl[:5, :5] = 9

    change = compare_spectral_scenes(old, new, old_scl, new_scl)

    assert change.mask[7, 7]
    assert change.cloud_mask[2, 2]
    assert not change.mask[2, 2]
    assert change.score[7, 7] >= change.threshold


def test_utm_grid_and_pixel_coordinates_cover_input_region() -> None:
    bbox = (73.82, 18.48, 73.90, 18.56)
    grid = create_target_grid(bbox)

    assert grid.crs == "EPSG:32643"
    assert grid.width > 0 and grid.height > 0
    latitude, longitude = pixel_center_wgs84(grid, grid.width / 2, grid.height / 2)
    bounds = pixel_bounds_wgs84(grid, 0, 0, grid.width, grid.height)
    assert bbox[1] < latitude < bbox[3]
    assert bbox[0] < longitude < bbox[2]
    assert bounds[0] <= latitude <= bounds[2]
    assert bounds[1] <= longitude <= bounds[3]
