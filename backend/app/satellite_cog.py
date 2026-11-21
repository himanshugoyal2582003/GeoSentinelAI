from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from typing import Any

import numpy as np
import planetary_computer
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine, from_origin
from rasterio.warp import reproject, transform as transform_coordinates, transform_bounds
from rasterio.windows import from_bounds

SENTINEL_BANDS = ("B02", "B03", "B04", "B08", "B11")
ASSET_KEYS = (*SENTINEL_BANDS, "SCL")


@dataclass(frozen=True)
class RasterGrid:
    transform: Affine
    width: int
    height: int
    crs: str
    resolution_m: float


@dataclass(frozen=True)
class Sentinel2Raster:
    bands: dict[str, np.ndarray]
    scl: np.ndarray
    grid: RasterGrid


def create_target_grid(bbox: tuple[float, float, float, float], resolution_m: float = 10) -> RasterGrid:
    """Create a north-up UTM grid for a WGS84 bbox at the requested pixel size."""
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox must be ordered WGS84 coordinates (west, south, east, north)")
    if resolution_m <= 0:
        raise ValueError("resolution_m must be positive")

    center_lon = (west + east) / 2
    center_lat = (south + north) / 2
    zone = min(60, max(1, floor((center_lon + 180) / 6) + 1))
    epsg = (32600 if center_lat >= 0 else 32700) + zone
    crs = f"EPSG:{epsg}"
    left, bottom, right, top = transform_bounds(
        "EPSG:4326",
        crs,
        west,
        south,
        east,
        north,
        densify_pts=21,
    )
    left = floor(left / resolution_m) * resolution_m
    top = ceil(top / resolution_m) * resolution_m
    width = max(1, ceil((right - left) / resolution_m))
    height = max(1, ceil((top - bottom) / resolution_m))
    return RasterGrid(
        transform=from_origin(left, top, resolution_m, resolution_m),
        width=width,
        height=height,
        crs=crs,
        resolution_m=resolution_m,
    )


def read_sentinel2_scene(
    item: dict[str, Any],
    bbox: tuple[float, float, float, float],
    grid: RasterGrid | None = None,
) -> Sentinel2Raster:
    """Read only the target bbox from Sentinel-2 L2A COG assets."""
    target_grid = grid or create_target_grid(bbox)
    if not isinstance(item.get("assets"), dict):
        raise ValueError("Sentinel-2 item has no assets")

    bands: dict[str, np.ndarray] = {}
    for band_name in SENTINEL_BANDS:
        asset = item["assets"].get(band_name)
        if not asset or not asset.get("href"):
            raise ValueError(f"Sentinel-2 item is missing required {band_name} COG asset")
        band = _read_asset_window(asset, bbox, target_grid, Resampling.bilinear)
        band_info = (asset.get("raster:bands") or [{}])[0]
        scale = float(band_info.get("scale", 1.0))
        offset = float(band_info.get("offset", 0.0))
        bands[band_name] = band * scale + offset

    scl_asset = item["assets"].get("SCL")
    if not scl_asset or not scl_asset.get("href"):
        raise ValueError("Sentinel-2 item is missing required SCL COG asset")
    scl = _read_asset_window(scl_asset, bbox, target_grid, Resampling.nearest)
    scl = np.nan_to_num(scl, nan=0).astype(np.uint8)
    return Sentinel2Raster(bands=bands, scl=scl, grid=target_grid)


def _read_asset_window(
    asset: dict[str, Any],
    bbox: tuple[float, float, float, float],
    grid: RasterGrid,
    resampling: Resampling,
) -> np.ndarray:
    signed_href = planetary_computer.sign_url(asset["href"])
    destination = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(signed_href) as dataset:
            source_bounds = transform_bounds(
                "EPSG:4326",
                dataset.crs,
                *bbox,
                densify_pts=21,
            )
            window = from_bounds(*source_bounds, transform=dataset.transform)
            window = window.round_offsets(op="floor").round_lengths(op="ceil")
            if window.width < 1 or window.height < 1:
                raise ValueError("Sentinel-2 asset does not overlap requested bbox")
            source = dataset.read(1, window=window, boundless=True, masked=True)
            source_array = np.asarray(source.astype(np.float32).filled(np.nan))
            reproject(
                source=source_array,
                destination=destination,
                src_transform=dataset.window_transform(window),
                src_crs=dataset.crs,
                src_nodata=np.nan,
                dst_transform=grid.transform,
                dst_crs=grid.crs,
                dst_nodata=np.nan,
                resampling=resampling,
                num_threads=1,
            )
    if not np.isfinite(destination).any():
        raise ValueError("Sentinel-2 asset contains no valid pixels for requested bbox")
    return destination


def rgb_preview(bands: dict[str, np.ndarray]) -> np.ndarray:
    """Create a contrast-stretched RGB preview from red, green, and blue bands."""
    rgb = np.stack([bands["B04"], bands["B03"], bands["B02"]], axis=2).astype(np.float32)
    preview = np.zeros_like(rgb, dtype=np.uint8)
    for channel in range(3):
        values = rgb[:, :, channel]
        finite = np.isfinite(values)
        if not finite.any():
            continue
        low, high = np.percentile(values[finite], [2, 98])
        if high <= low:
            high = low + 1
        stretched = np.clip((values - low) / (high - low), 0, 1)
        preview[:, :, channel] = np.nan_to_num(stretched * 255, nan=0).astype(np.uint8)
    return preview


def pixel_center_wgs84(grid: RasterGrid, column: float, row: float) -> tuple[float, float]:
    x, y = grid.transform @ (column, row)
    longitudes, latitudes = transform_coordinates(grid.crs, "EPSG:4326", [x], [y])
    return latitudes[0], longitudes[0]


def pixel_bounds_wgs84(
    grid: RasterGrid,
    x: int,
    y: int,
    width: int,
    height: int,
) -> list[float]:
    corners = [
        grid.transform @ (x, y),
        grid.transform @ (x + width, y),
        grid.transform @ (x, y + height),
        grid.transform @ (x + width, y + height),
    ]
    xs, ys = zip(*corners)
    longitudes, latitudes = transform_coordinates(grid.crs, "EPSG:4326", list(xs), list(ys))
    return [
        round(min(latitudes), 6),
        round(min(longitudes), 6),
        round(max(latitudes), 6),
        round(max(longitudes), 6),
    ]
