"""Pydantic v2 models for Scan entities."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ScanStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ScanCreate(BaseModel):
    """Fields required to create a new Scan node."""

    scan_id: str = Field(..., min_length=1, description="Unique scan identifier")
    mode: str = Field(..., min_length=1, description="Detection mode (e.g. live-sentinel2, upload)")
    region_id: str = Field(..., min_length=1, description="ID of the MonitoringRegion")
    historical_date: str = Field(..., description="Date of the historical scene (ISO date string)")
    recent_date: str = Field(..., description="Date of the recent scene (ISO date string)")
    changed_area_sqm: float = Field(..., ge=0, description="Total changed area in square metres")
    finding_count: int = Field(..., ge=0, description="Number of findings detected")
    model_name: str = Field(..., min_length=1, description="Name of the ML model used")
    processing_metadata: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    status: ScanStatus = ScanStatus.completed
    idempotency_key: str | None = Field(None, description="Optional idempotency key for dedup")


class Scan(ScanCreate):
    """Full Scan entity as stored in Neo4j."""

    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


class ScanSummary(BaseModel):
    """Lightweight summary returned in list endpoints."""

    scan_id: str
    created_at: datetime
    mode: str
    region_id: str
    changed_area_sqm: float
    finding_count: int
    model_name: str
    status: ScanStatus

    model_config = {"from_attributes": True}
