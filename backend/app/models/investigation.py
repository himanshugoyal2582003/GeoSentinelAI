"""Pydantic v2 models for InvestigationCase entities."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class CaseStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    closed = "closed"
    archived = "archived"


class InvestigationCreate(BaseModel):
    """Fields required to create an InvestigationCase node."""

    title: str = Field(..., min_length=1, max_length=500, description="Short human-readable title")
    description: str | None = Field(None, description="Detailed description of the investigation")
    status: CaseStatus = Field(default=CaseStatus.open)
    review_status: str = Field(default="pending")


class InvestigationCase(InvestigationCreate):
    """Full InvestigationCase entity as stored in Neo4j."""

    case_id: str = Field(..., min_length=1, description="Unique case identifier (UUID)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}
