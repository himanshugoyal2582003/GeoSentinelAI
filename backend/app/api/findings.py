"""Findings API router — finding details, spatial proximity, and history."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.neo4j import get_session
from app.repositories import finding_repository
from app.history import read_findings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/findings", tags=["findings"])


@router.get("")
def list_findings(
    scan_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List findings with optional scan_id filter, with CSV fallback."""
    try:
        with get_session() as session:
            if scan_id:
                findings = finding_repository.list_findings_for_scan(session, scan_id=scan_id)
            else:
                # Query recent findings
                result = session.run(
                    "MATCH (fo:FindingObservation) RETURN fo {.*} AS finding ORDER BY fo.created_at DESC SKIP $offset LIMIT $limit",
                    offset=offset,
                    limit=limit,
                )
                findings = [dict(record["finding"]) for record in result]
            return {"findings": findings, "count": len(findings), "source": "neo4j"}
    except Exception as exc:
        logger.warning("Neo4j query failed in list_findings, falling back to CSV: %s", exc)
        all_csv = read_findings(limit=limit + offset)
        if scan_id:
            all_csv = [f for f in all_csv if f.get("scan_id") == scan_id]
        paged = all_csv[offset : offset + limit]
        return {"findings": paged, "count": len(paged), "source": "csv"}


@router.get("/spatial-nearby")
def find_nearby_findings(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
    radius_m: float = Query(default=1000.0, ge=10.0, le=50000.0),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Retrieve observations within radius_m of a coordinate using WGS-84 spatial point."""
    try:
        with get_session() as session:
            nearby = finding_repository.find_in_radius(
                session, lat=lat, lon=lon, radius_m=radius_m, limit=limit
            )
            return {
                "center": {"latitude": lat, "longitude": lon},
                "radius_m": radius_m,
                "findings": nearby,
                "count": len(nearby),
            }
    except Exception as exc:
        logger.error("Failed to query nearby findings: %s", exc)
        raise HTTPException(status_code=500, detail="Database query failed.") from exc


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
