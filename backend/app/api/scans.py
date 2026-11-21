"""Scans API router — listing, pagination, and details."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.neo4j import get_session
from app.history import read_scans as _csv_read_scans
from app.repositories import scan_repository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.get("")
def list_scans(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    region_id: str | None = None,
) -> dict[str, Any]:
    """List scans with pagination.

    Attempts Neo4j first, falls back gracefully to CSV history if unavailable.
    """
    try:
        with get_session() as session:
            scans = scan_repository.list_scans(
                session, region_id=region_id, limit=limit, offset=offset
            )
            total = scan_repository.count_scans(session, region_id=region_id)
            return {"scans": scans, "total": total, "limit": limit, "offset": offset}
    except Exception as exc:
        logger.warning("Neo4j query failed in list_scans, falling back to CSV: %s", exc)
        return {"scans": _csv_read_scans(limit=limit)}


@router.get("/{scan_id}")
def get_scan(scan_id: str) -> dict[str, Any]:
    """Get a single scan by scan_id."""
    try:
        with get_session() as session:
            scan = scan_repository.get_scan(session, scan_id=scan_id)
            if not scan:
                raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found.")
            return scan
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch scan %s from Neo4j: %s", scan_id, exc)
        raise HTTPException(status_code=500, detail="Database query failed.") from exc
