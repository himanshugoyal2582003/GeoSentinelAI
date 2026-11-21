"""Pydantic v2 models for FindingObservation entities."""
from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class FindingCreate(BaseModel):
    """Fields required to create a new FindingObservation node."""

    detection_id: str = Field(..., min_length=1)
    original_finding_id: str = Field(..., min_length=1, description="Original id from the detection engine (e.g. GS-LIVE-001)")
    scan_id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    severity: Severity
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score in [0, 1]")
    area_sqm: float = Field(..., description="Detected changed area in square metres")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    first_observed: str = Field(..., description="ISO date string of historical scene")
    last_observed: str = Field(..., description="ISO date string of recent scene")
    change_type: str = Field(default="Spectral surface change")
    model_score: float | None = Field(None, ge=0.0, le=1.0)
    detection_error_sqm: float = Field(..., ge=0)
    region_bbox: list[float] = Field(..., description="[min_lat, min_lon, max_lat, max_lon]")
    review_status: str = Field(default="pending")

    @field_validator("confidence", "model_score", mode="before")
    @classmethod
    def _reject_nan_inf(cls, v: Any) -> Any:
        if v is None:
            return v
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise ValueError("Value must be a finite number")
        if math.isnan(f) or math.isinf(f):
            raise ValueError("Value must be finite (not NaN or Inf)")
        return f

    @field_validator("latitude", mode="before")
    @classmethod
    def _validate_lat(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("latitude is required")
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise ValueError("latitude must be a number")
        if math.isnan(f) or math.isinf(f):
            raise ValueError("latitude must be finite")
        return f

    @field_validator("longitude", mode="before")
    @classmethod
    def _validate_lon(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("longitude is required")
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise ValueError("longitude must be a number")
        if math.isnan(f) or math.isinf(f):
            raise ValueError("longitude must be finite")
        return f

    @field_validator("region_bbox")
    @classmethod
    def _validate_bbox(cls, v: list[float]) -> list[float]:
        if len(v) != 4:
            raise ValueError("region_bbox must have exactly 4 elements [min_lat, min_lon, max_lat, max_lon]")
        for val in v:
            if math.isnan(val) or math.isinf(val):
                raise ValueError("region_bbox values must be finite numbers")
        return v

    @field_validator("area_sqm", mode="before")
    @classmethod
    def _validate_area(cls, v: Any) -> Any:
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise ValueError("area_sqm must be a number")
        if math.isnan(f) or math.isinf(f):
            raise ValueError("area_sqm must be finite")
        return f


class FindingObservation(FindingCreate):
    """Full FindingObservation entity as stored in Neo4j."""

    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}
