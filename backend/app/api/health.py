"""Health and readiness API endpoints."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Response, status

from app.db.neo4j import verify_connectivity

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/api/health")
def health() -> dict[str, Any]:
    """Lightweight liveness probe — always returns 200 as long as process is up.

    Reports model status and current Neo4j reachability.
    """
    neo4j_info = verify_connectivity()
    neo4j_status = "connected" if neo4j_info.get("status") == "ok" else "unavailable"

    model_name = "difference-fallback"
    try:
        from pathlib import Path
        model_path = Path(__file__).resolve().parents[2] / "models" / "change_cnn.pt"
        if model_path.exists():
            model_name = "ChangeCNN"
    except Exception:
        pass

    return {
        "status": "ok",
        "service": "geosentinel-api",
        "model": model_name,
        "neo4j": neo4j_status,
    }


@router.get("/api/health/ready")
def readiness(response: Response) -> dict[str, Any]:
    """Readiness probe — returns 200 if database is reachable, 503 if not.

    Never claims readiness when Neo4j is unavailable.
    """
    neo4j_info = verify_connectivity()
    if neo4j_info.get("status") != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "service": "geosentinel-api",
            "database": "unavailable",
            "detail": neo4j_info.get("detail", "Neo4j connection could not be established"),
        }
    return {
        "status": "ready",
        "service": "geosentinel-api",
        "database": "connected",
    }
