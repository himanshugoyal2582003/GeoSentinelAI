"""Graph API router — region subgraph, stats, and intelligence queries."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.neo4j import get_driver, get_session
from app.services import graph_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/stats")
def get_graph_stats() -> dict[str, Any]:
    """Retrieve node counts and overview statistics for the Neo4j graph."""
    try:
        with get_session() as session:
            query = """
            OPTIONAL MATCH (r:MonitoringRegion)
            WITH count(DISTINCT r) AS regions
            OPTIONAL MATCH (s:Scan)
            WITH regions, count(DISTINCT s) AS scans
            OPTIONAL MATCH (fo:FindingObservation)
            WITH regions, scans, count(DISTINCT fo) AS findings
            OPTIONAL MATCH (sc:SatelliteScene)
            WITH regions, scans, findings, count(DISTINCT sc) AS scenes
            OPTIONAL MATCH (c:InvestigationCase)
            WITH regions, scans, findings, scenes, count(DISTINCT c) AS cases
            OPTIONAL MATCH (ea:EvidenceAsset)
            WITH regions, scans, findings, scenes, cases, count(DISTINCT ea) AS assets
            RETURN {
                regions: regions,
                scans: scans,
                findings: findings,
                scenes: scenes,
                cases: cases,
                assets: assets
            } AS stats
            """
            result = session.run(query)
            record = result.single()
            stats = record["stats"] if record else {}
            return {"status": "ok", "stats": stats}
    except Exception as exc:
        logger.warning("Failed to fetch graph stats: %s", exc)
        return {
            "status": "degraded",
            "message": "Neo4j unavailable, graph stats not accessible.",
            "error": str(exc),
        }


@router.get("/regions/{region_id}")
def get_region_graph(
    region_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Retrieve region entity and recent scan history."""
    try:
        driver = get_driver()
        data = graph_service.get_region_scan_history(
            driver, region_id=region_id, limit=limit, offset=offset
        )
        if not data.get("region"):
            raise HTTPException(status_code=404, detail=f"Region {region_id} not found.")
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to query region graph for %s: %s", region_id, exc)
        raise HTTPException(status_code=500, detail="Database query failed.") from exc


@router.get("/findings/{detection_id}/recommendations")
def recommend_related(
    detection_id: str,
    radius_m: float = Query(default=500.0, ge=10.0, le=10000.0),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    """Recommend nearby observations for human review (never auto-merged)."""
    try:
        driver = get_driver()
        candidates = graph_service.recommend_related_observations(
            driver, detection_id=detection_id, radius_m=radius_m, limit=limit
        )
        return {
            "detection_id": detection_id,
            "radius_m": radius_m,
            "candidates": candidates,
        }
    except Exception as exc:
        logger.error("Failed to get recommendations for %s: %s", detection_id, exc)
        raise HTTPException(status_code=500, detail="Database query failed.") from exc
