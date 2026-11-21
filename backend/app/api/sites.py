"""Monitoring-site API for user-defined polygon regions."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from app.db.neo4j import get_driver
from app.geometry import (
    MAX_IMPORT_BYTES,
    geometry_bbox,
    normalize_polygon_geometry,
    parse_geojson_upload,
    parse_kml_upload,
)
from app.repositories import region_repository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sites", tags=["sites"])


class CreateSiteRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    geometry: dict[str, Any]


def _site_response(region: dict[str, Any]) -> dict[str, Any]:
    geometry = region.get("geometry_geojson")
    if isinstance(geometry, str):
        geometry = json.loads(geometry)
    bbox = region.get("bbox")
    if isinstance(bbox, str):
        bbox = json.loads(bbox)
    return {
        "siteId": region["region_id"],
        "name": region.get("name", ""),
        "geometry": geometry,
        "bbox": bbox,
        "active": region.get("active", True),
    }


def _create_site(name: str, geometry_value: Any) -> dict[str, Any]:
    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(status_code=422, detail="Site name must not be blank.")
    try:
        geometry = normalize_polygon_geometry(geometry_value)
        bbox = geometry_bbox(geometry)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    region_id = f"site-{uuid4().hex}"
    now = datetime.now(timezone.utc).isoformat()
    try:
        with get_driver().session() as session:
            region_repository.merge_region(
                session,
                {
                    "region_id": region_id,
                    "name": normalized_name,
                    "description": "User-defined polygon monitoring site",
                    "bbox": list(bbox),
                    "geometry_geojson": json.dumps(geometry),
                    "is_monitoring_site": True,
                    "created_at": now,
                },
            )
        return {
            "siteId": region_id,
            "name": normalized_name,
            "geometry": geometry,
            "bbox": list(bbox),
            "active": True,
        }
    except Exception as exc:
        logger.exception("Failed to create monitoring site")
        raise HTTPException(status_code=503, detail="Monitoring site storage is unavailable.") from exc


@router.get("")
def list_sites(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    try:
        with get_driver().session() as session:
            sites = region_repository.list_sites(session, limit=limit, offset=offset)
        return {
            "sites": [_site_response(site) for site in sites],
            "limit": limit,
            "offset": offset,
        }
    except Exception as exc:
        logger.exception("Failed to list monitoring sites")
        raise HTTPException(status_code=503, detail="Monitoring site storage is unavailable.") from exc


@router.post("", status_code=201)
def create_site(request: CreateSiteRequest) -> dict[str, Any]:
    return _create_site(request.name, request.geometry)


@router.post("/import", status_code=201)
async def import_site(
    name: str = Form(..., min_length=1, max_length=120),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    filename = (file.filename or "").lower()
    content = await file.read(MAX_IMPORT_BYTES + 1)
    try:
        if filename.endswith(".kml"):
            geometry = parse_kml_upload(content)
        elif filename.endswith((".geojson", ".json")):
            geometry = parse_geojson_upload(content)
        else:
            raise ValueError("Upload a .kml, .geojson, or .json polygon file.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()
    return _create_site(name, geometry)


@router.get("/{site_id}")
def get_site(site_id: str) -> dict[str, Any]:
    try:
        with get_driver().session() as session:
            region = region_repository.get_region(session, site_id)
        if not region or not region.get("is_monitoring_site") or region.get("active") is False:
            raise HTTPException(status_code=404, detail="Monitoring site not found.")
        return _site_response(region)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to retrieve monitoring site %s", site_id)
        raise HTTPException(status_code=503, detail="Monitoring site storage is unavailable.") from exc


@router.delete(
    "/{site_id}",
    status_code=204,
    response_class=Response,
    response_model=None,
)
def delete_site(site_id: str) -> None:
    try:
        with get_driver().session() as session:
            deleted = region_repository.deactivate_site(session, site_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Monitoring site not found.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete monitoring site %s", site_id)
        raise HTTPException(status_code=503, detail="Monitoring site storage is unavailable.") from exc
