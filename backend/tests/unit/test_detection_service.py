"""Unit tests for detection service validation helpers."""
from __future__ import annotations

import numpy as np
import pytest
from fastapi import HTTPException

from app.services.detection_service import (
    validate_coordinates,
    validate_image_pair,
    validate_pixel_size,
)


class TestDetectionValidation:
    def test_valid_image_pair(self):
        img1 = np.zeros((100, 100, 3), dtype=np.float32)
        img2 = np.ones((100, 100, 3), dtype=np.float32)
        # Should not raise
        validate_image_pair(img1, img2)

    def test_empty_image_raises_400(self):
        img1 = np.zeros((0, 0, 3), dtype=np.float32)
        img2 = np.ones((100, 100, 3), dtype=np.float32)
        with pytest.raises(HTTPException) as exc_info:
            validate_image_pair(img1, img2)
        assert exc_info.value.status_code == 400

    def test_mismatched_dimensions_raises_400(self):
        img1 = np.zeros((100, 100, 3), dtype=np.float32)
        img2 = np.ones((100, 120, 3), dtype=np.float32)
        with pytest.raises(HTTPException) as exc_info:
            validate_image_pair(img1, img2)
        assert exc_info.value.status_code == 400

    def test_oversized_image_raises_413(self):
        # > 4 megapixels = 2001 x 2001 = 4,004,001 pixels
        img1 = np.zeros((2001, 2001, 3), dtype=np.float32)
        img2 = np.zeros((2001, 2001, 3), dtype=np.float32)
        with pytest.raises(HTTPException) as exc_info:
            validate_image_pair(img1, img2)
        assert exc_info.value.status_code == 413

    def test_valid_coordinates(self):
        validate_coordinates(18.5204, 73.8567)
        validate_coordinates(-90.0, -180.0)
        validate_coordinates(90.0, 180.0)

    def test_invalid_lat_nan_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_coordinates(float("nan"), 73.0)
        assert exc_info.value.status_code == 422

    def test_invalid_lat_out_of_range_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_coordinates(91.0, 73.0)
        assert exc_info.value.status_code == 422

    def test_invalid_lon_out_of_range_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_coordinates(18.0, 181.0)
        assert exc_info.value.status_code == 422

    def test_pixel_size_valid(self):
        validate_pixel_size(10.0)
        validate_pixel_size(0.5)

    def test_pixel_size_zero_or_negative_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_pixel_size(0.0)
        assert exc_info.value.status_code == 422

        with pytest.raises(HTTPException) as exc_info:
            validate_pixel_size(-5.0)
        assert exc_info.value.status_code == 422
