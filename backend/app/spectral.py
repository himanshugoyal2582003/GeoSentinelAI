from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CLOUD_SCL_CLASSES = (0, 1, 3, 7, 8, 9, 10, 11)
MIN_CHANGE_DELTA = 0.10


@dataclass(frozen=True)
class SpectralChange:
    mask: np.ndarray
    score: np.ndarray
    ndvi_loss: np.ndarray
    bsi_gain: np.ndarray
    cloud_mask: np.ndarray
    threshold: float


def calculate_indices(bands: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Return NDVI and Bare Soil Index from Sentinel-2 surface reflectance bands."""
    blue = np.asarray(bands["B02"], dtype=np.float32)
    red = np.asarray(bands["B04"], dtype=np.float32)
    nir = np.asarray(bands["B08"], dtype=np.float32)
    swir = np.asarray(bands["B11"], dtype=np.float32)
    ndvi = _safe_ratio(nir - red, nir + red)
    bsi = _safe_ratio((swir + red) - (nir + blue), (swir + red) + (nir + blue))
    return np.clip(ndvi, -1, 1), np.clip(bsi, -1, 1)


def scl_cloud_mask(scl: np.ndarray) -> np.ndarray:
    """Mask SCL no-data, shadow, unclassified, cloud, cirrus, and snow classes."""
    return np.isin(scl, CLOUD_SCL_CLASSES)


def compare_spectral_scenes(
    old_bands: dict[str, np.ndarray],
    new_bands: dict[str, np.ndarray],
    old_scl: np.ndarray,
    new_scl: np.ndarray,
    alignment_shift: tuple[float, float] = (0, 0),
    min_change_delta: float = MIN_CHANGE_DELTA,
) -> SpectralChange:
    old_ndvi, old_bsi = calculate_indices(old_bands)
    new_ndvi, new_bsi = calculate_indices(new_bands)
    shift_x, shift_y = (int(round(alignment_shift[0])), int(round(alignment_shift[1])))
    if shift_x or shift_y:
        new_ndvi = np.roll(new_ndvi, (shift_y, shift_x), axis=(0, 1))
        new_bsi = np.roll(new_bsi, (shift_y, shift_x), axis=(0, 1))
        new_scl = np.roll(new_scl, (shift_y, shift_x), axis=(0, 1))

    cloud_mask = scl_cloud_mask(old_scl) | scl_cloud_mask(new_scl)
    ndvi_loss = np.maximum(old_ndvi - new_ndvi, 0)
    bsi_gain = np.maximum(new_bsi - old_bsi, 0)
    score = np.maximum(ndvi_loss, bsi_gain)
    valid = ~cloud_mask & np.isfinite(score)
    threshold = max(min_change_delta, float(np.percentile(score[valid], 90))) if valid.any() else min_change_delta
    mask = valid & (score >= threshold)
    return SpectralChange(
        mask=mask,
        score=np.nan_to_num(score, nan=0.0),
        ndvi_loss=np.nan_to_num(ndvi_loss, nan=0.0),
        bsi_gain=np.nan_to_num(bsi_gain, nan=0.0),
        cloud_mask=cloud_mask | ~np.isfinite(score),
        threshold=threshold,
    )


def _safe_ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    result = np.zeros_like(numerator, dtype=np.float32)
    return np.divide(
        numerator,
        denominator,
        out=result,
        where=np.isfinite(denominator) & (np.abs(denominator) > 1e-6),
    )
