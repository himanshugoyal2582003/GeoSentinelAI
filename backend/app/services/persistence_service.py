"""Persistence service — saves a complete scan result to Neo4j (and CSV as fallback).

All Neo4j writes happen inside ONE write transaction; any failure rolls back
completely so we never store partial data.

The CSV save_scan() call is best-effort: a failure there is logged as a warning
but does NOT raise, so the detection response is unaffected.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# CSV backward-compat — always importable
from app.history import save_scan as _csv_save_scan

# ---------------------------------------------------------------------------
# Cypher: batch-create findings and wire all relationships in one tx
# ---------------------------------------------------------------------------

_MERGE_REGION = """
MERGE (r:MonitoringRegion {region_id: $region_id})
ON CREATE SET
    r.name       = $name,
    r.bbox       = $bbox,
    r.geometry_geojson = $geometry_geojson,
    r.is_monitoring_site = $is_monitoring_site,
    r.active     = true,
    r.created_at = $created_at
ON MATCH SET
    r.name       = coalesce($name, r.name),
    r.bbox       = coalesce($bbox, r.bbox),
    r.geometry_geojson = coalesce($geometry_geojson, r.geometry_geojson),
    r.is_monitoring_site = coalesce($is_monitoring_site, r.is_monitoring_site),
    r.active     = true
RETURN r.region_id AS region_id
"""

_MERGE_SCAN = """
MERGE (s:Scan {scan_id: $scan_id})
ON CREATE SET
    s.idempotency_key     = $idempotency_key,
    s.region_id           = $region_id,
    s.mode                = $mode,
    s.status              = $status,
    s.historical_date     = $historical_date,
    s.recent_date         = $recent_date,
    s.changed_area_sqm    = $changed_area_sqm,
    s.finding_count       = $finding_count,
    s.model_name          = $model_name,
    s.created_at          = $created_at,
    s.processing_metadata = $processing_metadata,
    s.summary             = $summary,
    s.source_metadata     = $source_metadata
RETURN s.scan_id AS scan_id
"""

_LINK_REGION_SCAN = """
MATCH (r:MonitoringRegion {region_id: $region_id})
MATCH (s:Scan {scan_id: $scan_id})
MERGE (r)-[:HAS_SCAN]->(s)
"""

_MERGE_SCENE = """
MERGE (sc:SatelliteScene {scene_id: $scene_id})
ON CREATE SET
    sc.provider     = $provider,
    sc.acquired_at  = $acquired_at,
    sc.cloud_cover  = $cloud_cover,
    sc.created_at   = $created_at
RETURN sc.scene_id AS scene_id
"""

_LINK_SCAN_SCENE = """
MATCH (s:Scan {scan_id: $scan_id})
MATCH (sc:SatelliteScene {scene_id: $scene_id})
MERGE (s)-[:USED_SCENE {role: $role}]->(sc)
"""

_BATCH_FINDINGS = """
UNWIND $findings AS f
MERGE (d:FindingObservation {detection_id: f.detection_id})
ON CREATE SET
    d.original_finding_id  = f.original_finding_id,
    d.scan_id              = f.scan_id,
    d.label                = f.label,
    d.severity             = f.severity,
    d.confidence           = f.confidence,
    d.area_sqm             = f.area_sqm,
    d.latitude             = f.latitude,
    d.longitude            = f.longitude,
    d.location             = point({latitude: f.latitude, longitude: f.longitude, crs: 'WGS-84'}),
    d.first_observed       = f.first_observed,
    d.last_observed        = f.last_observed,
    d.change_type          = f.change_type,
    d.model_score          = f.model_score,
    d.detection_error_sqm  = f.detection_error_sqm,
    d.region_bbox          = f.region_bbox,
    d.review_status        = f.review_status,
    d.created_at           = f.created_at
WITH d, f
MATCH (s:Scan {scan_id: f.scan_id})
MERGE (s)-[:PRODUCED]->(d)
"""


def _make_detection_id(scan_id: str, finding_id: str) -> str:
    return f"det-{scan_id}-{finding_id}"


def _safe_json_str(obj: Any) -> str:
    """Serialize to JSON string; fall back to '{}' on failure."""
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        return "{}"


def persist_scan(
    driver: Any,
    result: dict[str, Any],
    source: dict[str, Any],
    mode: str,
    idempotency_key: str | None = None,
) -> str:
    """Persist a complete scan result to Neo4j.

    Returns the scan_id (newly created or existing if idempotent replay).
    Raises RuntimeError on Neo4j write failure (CSV is best-effort only).
    """
    # 1. Idempotency guard
    if idempotency_key:
        existing = _get_scan_by_idempotency_key(driver, idempotency_key)
        if existing:
            logger.info("Idempotent replay: returning existing scan %s", existing)
            return existing

    # 2. Build scan_id
    now = datetime.now(timezone.utc).isoformat()
    scan_id = result.get("scanId") or f"scan-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"

    # 3. Derive region info
    region_name = result.get("region", "Pune quarry belt")
    bbox = source.get("bbox", [73.82, 18.48, 73.90, 18.56])
    region_id = result.get("regionId") or f"region-{region_name.lower().replace(' ', '-')}"
    geometry = source.get("geometry")

    # 4. Build findings payload
    raw_findings = result.get("findings", [])
    findings_payload = []
    for f in raw_findings:
        coords = f.get("coordinates", [0.0, 0.0])
        lat = float(coords[0]) if len(coords) > 0 else 0.0
        lon = float(coords[1]) if len(coords) > 1 else 0.0
        detection_id = _make_detection_id(scan_id, str(f.get("id", uuid4().hex[:8])))
        # Also enrich finding in result dictionary with detection_id
        f["detection_id"] = detection_id
        findings_payload.append({
            "detection_id": detection_id,
            "original_finding_id": str(f.get("id", "")),
            "scan_id": scan_id,
            "label": f.get("label", ""),
            "severity": f.get("severity", "low"),
            "confidence": float(f.get("confidence", 0.0)),
            "area_sqm": int(f.get("areaSqm", 0)),
            "latitude": lat,
            "longitude": lon,
            "first_observed": f.get("firstObserved", ""),
            "last_observed": f.get("lastObserved", ""),
            "change_type": f.get("changeType", "Spectral surface change"),
            "model_score": f.get("modelScore"),
            "detection_error_sqm": int(f.get("detectionErrorSqm", 0)),
            "region_bbox": f.get("regionBbox", []),
            "review_status": f.get("status", "Needs review"),
            "created_at": now,
        })

    # 5. Single write transaction — rolls back on any failure
    try:
        with driver.session() as session:
            session.execute_write(_write_all, {
                "scan_id": scan_id,
                "idempotency_key": idempotency_key,
                "region_id": region_id,
                "region_name": region_name,
                "bbox": _safe_json_str(bbox),
                "geometry_geojson": _safe_json_str(geometry) if geometry else None,
                "is_monitoring_site": bool(result.get("regionId")),
                "mode": mode,
                "historical_date": result.get("historicalDate", ""),
                "recent_date": result.get("recentDate", ""),
                "changed_area_sqm": int(result.get("summary", {}).get("changedAreaSqm", 0)),
                "finding_count": len(raw_findings),
                "model_name": result.get("processing", {}).get("model", "unknown"),
                "processing_metadata": _safe_json_str(result.get("processing", {})),
                "summary": _safe_json_str(result.get("summary", {})),
                "source_metadata": _safe_json_str(source),
                "now": now,
                "findings": findings_payload,
                "historical_scene_id": source.get("historicalItem"),
                "recent_scene_id": source.get("recentItem"),
                "provider": source.get("provider", "Microsoft Planetary Computer / Copernicus Sentinel-2 L2A"),
                "historical_cloud_cover": source.get("historicalCloudCover"),
                "recent_cloud_cover": source.get("recentCloudCover"),
                "historical_date_str": result.get("historicalDate", ""),
                "recent_date_str": result.get("recentDate", ""),
            })
    except Exception as exc:
        raise RuntimeError(f"Neo4j write failed: {exc}") from exc

    # 6. CSV best-effort (non-blocking)
    def _csv_write() -> None:
        try:
            _csv_save_scan(result, source)
        except Exception as csv_exc:
            logger.warning("CSV fallback save failed (non-fatal): %s", csv_exc)

    threading.Thread(target=_csv_write, daemon=True).start()

    return scan_id


def _write_all(tx: Any, p: dict[str, Any]) -> None:
    """Execute all Neo4j writes in a single transaction (called via execute_write)."""
    # Region
    r = tx.run(_MERGE_REGION, name=p["region_name"], region_id=p["region_id"],
               bbox=p["bbox"], geometry_geojson=p["geometry_geojson"],
               is_monitoring_site=p["is_monitoring_site"], created_at=p["now"])
    r.consume()

    # Scan
    s = tx.run(_MERGE_SCAN,
               scan_id=p["scan_id"],
               idempotency_key=p["idempotency_key"],
               region_id=p["region_id"],
               mode=p["mode"],
               status="completed",
               historical_date=p["historical_date"],
               recent_date=p["recent_date"],
               changed_area_sqm=p["changed_area_sqm"],
               finding_count=p["finding_count"],
               model_name=p["model_name"],
               created_at=p["now"],
               processing_metadata=p["processing_metadata"],
               summary=p["summary"],
               source_metadata=p["source_metadata"])
    s.consume()

    # (MonitoringRegion)-[:HAS_SCAN]->(Scan)
    lr = tx.run(_LINK_REGION_SCAN, scan_id=p["scan_id"], region_id=p["region_id"])
    lr.consume()

    # (Scan)-[:USED_SCENE]->(SatelliteScene)
    for scene_id, role, acquired_at, cloud_cover in [
        (p["historical_scene_id"], "historical", p["historical_date_str"], p["historical_cloud_cover"]),
        (p["recent_scene_id"], "recent", p["recent_date_str"], p["recent_cloud_cover"]),
    ]:
        if scene_id:
            sc = tx.run(_MERGE_SCENE, scene_id=scene_id, provider=p["provider"],
                        acquired_at=acquired_at, cloud_cover=cloud_cover,
                        created_at=p["now"])
            sc.consume()
            lsc = tx.run(_LINK_SCAN_SCENE, scan_id=p["scan_id"],
                         scene_id=scene_id, role=role)
            lsc.consume()

    # Findings: (Scan)-[:PRODUCED]->(FindingObservation)
    if p["findings"]:
        f = tx.run(_BATCH_FINDINGS, findings=p["findings"])
        f.consume()


def _get_scan_by_idempotency_key(driver: Any, key: str) -> str | None:
    """Return scan_id for an existing idempotency key, or None."""
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (s:Scan {idempotency_key: $key}) RETURN s.scan_id AS sid",
                key=key,
            )
            record = result.single()
            return record["sid"] if record else None
    except Exception:
        return None
