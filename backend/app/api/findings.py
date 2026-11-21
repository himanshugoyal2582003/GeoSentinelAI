"""Findings API router — finding details and spatial history."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.neo4j import get_session
from app.repositories import finding_repository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/findings", tags=["findings"])


@router.get("/{detection_id}")
def get_finding(detection_id: str) -> dict[str, Any]:
    """Retrieve details for a single FindingObservation."""
    try:
        with get_session() as session:
            finding = finding_repository.get_finding(session, detection_id=detection_id)
            if not finding:
                raise HTTPException(status_code=404, detail=f"Finding {detection_id} not found.")
            return finding
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch finding %s: %s", detection_id, exc)
        raise HTTPException(status_code=500, detail="Database query failed.") from exc


@router.get("/{detection_id}/history")
def get_finding_history(
    detection_id: str,
    radius_m: float = Query(default=500.0, ge=10.0, le=10000.0),
) -> dict[str, Any]:
    """Retrieve historical observations across different scans within a radius."""
    try:
        with get_session() as session:
            history = finding_repository.get_finding_history(
                session, detection_id=detection_id, radius_m=radius_m
            )
            return {
                "detection_id": detection_id,
                "radius_m": radius_m,
                "related_observations": history,
            }
    except Exception as exc:
        logger.error("Failed to query history for finding %s: %s", detection_id, exc)
        raise HTTPException(status_code=500, detail="Database query failed.") from exc
