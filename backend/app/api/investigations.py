"""Investigations API router — case management and observation associations."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.neo4j import get_driver
from app.services import investigation_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/investigations", tags=["investigations"])


class CreateCaseRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    status: str = "open"
    review_status: str = "pending"


class AssociateObservationRequest(BaseModel):
    detection_id: str = Field(..., min_length=1)


@router.get("")
def list_investigations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List investigation cases."""
    try:
        driver = get_driver()
        cases = investigation_service.list_investigations(driver, limit=limit, offset=offset)
        return {"cases": cases, "limit": limit, "offset": offset}
    except Exception as exc:
        logger.error("Failed to list investigations: %s", exc)
        raise HTTPException(status_code=500, detail="Database query failed.") from exc


@router.post("", status_code=201)
def create_investigation(req: CreateCaseRequest) -> dict[str, Any]:
    """Create a new investigation case."""
    try:
        driver = get_driver()
        case = investigation_service.create_investigation(
            driver,
            title=req.title,
            description=req.description,
            status=req.status,
            review_status=req.review_status,
        )
        return case
    except Exception as exc:
        logger.error("Failed to create investigation case: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create case.") from exc


@router.get("/{case_id}")
def get_investigation(case_id: str) -> dict[str, Any]:
    """Get details of an investigation case and its linked observations."""
    try:
        driver = get_driver()
        case = investigation_service.get_investigation(driver, case_id=case_id)
        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")
        return case
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get case %s: %s", case_id, exc)
        raise HTTPException(status_code=500, detail="Database query failed.") from exc


@router.post("/{case_id}/observations", status_code=200)
def associate_observation(case_id: str, req: AssociateObservationRequest) -> dict[str, Any]:
    """Associate a finding observation with an investigation case (idempotent)."""
    try:
        driver = get_driver()
        result = investigation_service.add_observation_to_case(
            driver, case_id=case_id, detection_id=req.detection_id
        )
        return result
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err)) from val_err
    except Exception as exc:
        logger.error("Failed to associate observation with case %s: %s", case_id, exc)
        raise HTTPException(status_code=500, detail="Failed to link observation.") from exc
