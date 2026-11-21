"""Pydantic v2 models for EvidenceAsset entities."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AssetType = Literal["historical_image", "recent_image", "diff_image", "report", "other"]


class EvidenceAssetCreate(BaseModel):
    """Fields required to create an EvidenceAsset node."""

    asset_id: str = Field(..., min_length=1, description="Unique asset identifier (UUID)")
    uri: str = Field(..., min_length=1, description="Storage URI (local path or object-store key)")
    sha256: str = Field(..., min_length=64, max_length=64, description="SHA-256 hex digest of the file")
    media_type: str = Field(..., min_length=1, description="MIME type (e.g. image/png)")
    file_size: int = Field(..., ge=0, description="File size in bytes")
    asset_type: AssetType = Field(..., description="Role of this asset")


class EvidenceAsset(EvidenceAssetCreate):
    """Full EvidenceAsset entity as stored in Neo4j."""

    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}
