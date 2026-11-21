"""Pydantic v2 models for SatelliteScene entities."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SceneCreate(BaseModel):
    """Fields required to create a SatelliteScene node."""

    scene_id: str = Field(..., min_length=1, description="Provider scene identifier")
    provider: str = Field(..., min_length=1, description="Data provider (e.g. Microsoft Planetary Computer)")
    acquired_at: datetime = Field(..., description="Scene acquisition timestamp")
    cloud_cover: float | None = Field(None, ge=0.0, le=100.0, description="Cloud cover percentage")
    asset_metadata: dict[str, Any] = Field(default_factory=dict, description="Raw provider metadata")


class SatelliteScene(SceneCreate):
    """Full SatelliteScene entity as stored in Neo4j."""

    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}
