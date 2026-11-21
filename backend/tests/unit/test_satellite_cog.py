from __future__ import annotations

import numpy as np
import pytest
import rasterio
from rasterio.enums import Resampling

from app.satellite_cog import ASSET_KEYS, _read_asset_window, create_target_grid, read_sentinel2_scene


def test_reads_reflectance_and_scl_into_common_10m_grid(tmp_path, monkeypatch) -> None:
    bbox = (73.82, 18.48, 73.90, 18.56)
    grid = create_target_grid(bbox, resolution_m=10)
    assets = {}
    profile = {
        "driver": "GTiff",
        "height": grid.height,
        "width": grid.width,
        "count": 1,
        "crs": grid.crs,
        "transform": grid.transform,
        "nodata": 0,
    }

    for band_name in ASSET_KEYS:
        path = tmp_path / f"{band_name}.tif"
        dtype = "uint8" if band_name == "SCL" else "uint16"
        values = np.full(
            (grid.height, grid.width),
            4 if band_name == "SCL" else 1000,
            dtype=dtype,
        )
        with rasterio.open(path, "w", **(profile | {"dtype": dtype})) as dataset:
            dataset.write(values, 1)
        assets[band_name] = {
            "href": str(path),
            "raster:bands": [{"scale": 0.0001, "offset": 0}] if band_name != "SCL" else [],
        }

    monkeypatch.setattr("app.satellite_cog.planetary_computer.sign_url", lambda href: href)
    result = read_sentinel2_scene({"assets": assets}, bbox, grid)

    assert result.grid == grid
    assert result.bands["B08"].shape == (grid.height, grid.width)
    finite = np.isfinite(result.bands["B08"])
    assert finite.any()
    assert np.isnan(result.bands["B08"]).any()
    assert np.allclose(result.bands["B08"][finite], 0.1)
    assert np.all(result.scl[finite] == 4)
    assert np.all(result.scl[~finite] == 0)

    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [73.82, 18.48],
            [73.86, 18.48],
            [73.86, 18.56],
            [73.82, 18.56],
            [73.82, 18.48],
        ]],
    }
    clipped = read_sentinel2_scene({"assets": assets}, bbox, grid, geometry)
    outside = ~np.isfinite(clipped.bands["B08"])
    assert outside.any()
    assert np.isfinite(clipped.bands["B08"]).any()
    assert np.all(clipped.scl[outside] == 0)


def test_rejects_asset_window_without_valid_pixels(tmp_path, monkeypatch) -> None:
    bbox = (73.82, 18.48, 73.90, 18.56)
    grid = create_target_grid(bbox)
    path = tmp_path / "empty.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=grid.height,
        width=grid.width,
        count=1,
        dtype="uint16",
        crs=grid.crs,
        transform=grid.transform,
        nodata=0,
    ) as dataset:
        dataset.write(np.zeros((grid.height, grid.width), dtype=np.uint16), 1)

    monkeypatch.setattr("app.satellite_cog.planetary_computer.sign_url", lambda href: href)

    with pytest.raises(ValueError, match="no valid pixels"):
        _read_asset_window({"href": str(path)}, bbox, grid, Resampling.bilinear)
