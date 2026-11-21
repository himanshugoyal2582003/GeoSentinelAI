"""
Detection service — pure input validation helpers extracted from main.py.
These run BEFORE expensive processing so failures are fast.
"""
from __future__ import annotations

import math

import numpy as np
from fastapi import HTTPException


def validate_image_pair(old_arr: np.ndarray, new_arr: np.ndarray) -> None:
    """Raise HTTPException if the image pair is not usable."""
    if old_arr.size == 0 or new_arr.size == 0:
        raise HTTPException(status_code=400, detail="Images must not be empty.")
    if old_arr.shape != new_arr.shape:
        raise HTTPException(
            status_code=400,
            detail="Historical and recent images must have identical dimensions.",
        )
    h, w = old_arr.shape[:2]
    if h * w > 4_000_000:
        raise HTTPException(
            status_code=413,
            detail="Images must be at most 4 megapixels for this MVP.",
        )


def validate_coordinates(lat: float, lon: float) -> None:
    """Raise HTTPException if latitude/longitude are out of range or non-finite."""
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise HTTPException(
            status_code=422,
            detail="Latitude and longitude must be finite numbers (no NaN or Inf).",
        )
    if not (-90.0 <= lat <= 90.0):
        raise HTTPException(
            status_code=422,
            detail=f"Latitude must be in [-90, 90]; got {lat}.",
        )
    if not (-180.0 <= lon <= 180.0):
        raise HTTPException(
            status_code=422,
            detail=f"Longitude must be in [-180, 180]; got {lon}.",
        )


def validate_pixel_size(px: float) -> None:
    """Raise HTTPException if pixel size is non-positive or non-finite."""
    if not math.isfinite(px) or px <= 0:
        raise HTTPException(
            status_code=422,
            detail=f"pixel_size_m must be a positive finite number; got {px}.",
        )
