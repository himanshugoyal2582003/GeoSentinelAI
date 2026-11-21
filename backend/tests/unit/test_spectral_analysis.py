from __future__ import annotations

import numpy as np
from rasterio.transform import from_origin

from app.main import _analyse_scene_pair
from app.satellite_cog import RasterGrid, Sentinel2Raster


def test_scene_pair_uses_spectral_mask_and_georeferenced_coordinates(monkeypatch) -> None:
    shape = (64, 64)
    old_bands = {
        "B02": np.full(shape, 0.1, dtype=np.float32),
        "B03": np.full(shape, 0.2, dtype=np.float32),
        "B04": np.full(shape, 0.2, dtype=np.float32),
        "B08": np.full(shape, 0.6, dtype=np.float32),
        "B11": np.full(shape, 0.5, dtype=np.float32),
    }
    new_bands = {name: values.copy() for name, values in old_bands.items()}
    new_bands["B04"][20:30, 20:30] = 0.6
    new_bands["B08"][20:30, 20:30] = 0.2
    scl = np.full(shape, 5, dtype=np.uint8)
    grid = RasterGrid(from_origin(400000, 2100000, 10, 10), 64, 64, "EPSG:32643", 10)
    historical = Sentinel2Raster(old_bands, scl, grid)
    recent = Sentinel2Raster(new_bands, scl, grid)
    monkeypatch.setattr("app.main.CHANGE_MODEL", None)

    result = _analyse_scene_pair(historical, recent, "2025-01-01", "2025-02-01", "live-sentinel2")

    assert result["findings"]
    finding = result["findings"][0]
    assert finding["changeType"] in {"Vegetation loss", "Bare-soil exposure"}
    assert 18 < finding["coordinates"][0] < 20
    assert 73 < finding["coordinates"][1] < 75
    assert result["processing"]["spectralIndices"] == ["NDVI", "BSI"]
