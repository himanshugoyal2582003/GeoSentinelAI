"""
Finding repository — parameterized Cypher only, no f-string injection.
Spatial queries use Neo4j point() with WGS-84 CRS.
"""
from __future__ import annotations

from neo4j import Session
from neo4j.exceptions import ServiceUnavailable, TransientError

# ---------------------------------------------------------------------------
# Cypher constants
# ---------------------------------------------------------------------------

_CREATE_FINDINGS_BATCH = """
UNWIND $findings AS f
MERGE (fo:FindingObservation {detection_id: f.detection_id})
ON CREATE SET
    fo.original_finding_id  = f.original_finding_id,
    fo.scan_id              = f.scan_id,
    fo.label                = f.label,
    fo.severity             = f.severity,
    fo.confidence           = f.confidence,
    fo.area_sqm             = f.area_sqm,
    fo.latitude             = f.latitude,
    fo.longitude            = f.longitude,
    fo.location             = point({latitude: f.latitude, longitude: f.longitude, crs: 'WGS-84'}),
    fo.first_observed       = f.first_observed,
    fo.last_observed        = f.last_observed,
    fo.change_type          = f.change_type,
    fo.model_score          = f.model_score,
    fo.detection_error_sqm  = f.detection_error_sqm,
    fo.region_bbox          = f.region_bbox,
    fo.review_status        = f.review_status,
    fo.created_at           = f.created_at
RETURN fo.detection_id AS detection_id
"""

_GET_FINDING = """
MATCH (fo:FindingObservation {detection_id: $detection_id})
RETURN fo {.*} AS finding
"""

_LIST_FINDINGS_FOR_SCAN = """
MATCH (fo:FindingObservation {scan_id: $scan_id})
RETURN fo {.*} AS finding
ORDER BY fo.confidence DESC
"""

_GET_FINDING_HISTORY = """
MATCH (fo:FindingObservation {detection_id: $detection_id})
WITH fo
MATCH (other:FindingObservation)
WHERE other.detection_id <> fo.detection_id
  AND point.distance(
        point({latitude: fo.latitude, longitude: fo.longitude, crs: 'WGS-84'}),
        point({latitude: other.latitude, longitude: other.longitude, crs: 'WGS-84'})
      ) <= $radius_m
RETURN other {.*} AS finding,
       point.distance(
           point({latitude: fo.latitude, longitude: fo.longitude, crs: 'WGS-84'}),
           point({latitude: other.latitude, longitude: other.longitude, crs: 'WGS-84'})
       ) AS distance_m
ORDER BY other.created_at DESC
"""

_FIND_IN_RADIUS = """
WITH point({latitude: $lat, longitude: $lon, crs: 'WGS-84'}) AS center
MATCH (fo:FindingObservation)
WHERE point.distance(
        point({latitude: fo.latitude, longitude: fo.longitude, crs: 'WGS-84'}),
        center
      ) <= $radius_m
RETURN fo {.*} AS finding,
       point.distance(
           point({latitude: fo.latitude, longitude: fo.longitude, crs: 'WGS-84'}),
           center
       ) AS distance_m
ORDER BY distance_m ASC
LIMIT $limit
"""

_FIND_IN_BBOX = """
MATCH (fo:FindingObservation)
WHERE fo.latitude  >= $min_lat
  AND fo.latitude  <= $max_lat
  AND fo.longitude >= $min_lon
  AND fo.longitude <= $max_lon
RETURN fo {.*} AS finding
ORDER BY fo.confidence DESC
LIMIT $limit
"""


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------

def create_findings_batch(session: Session, findings: list[dict]) -> list[str]:
    """UNWIND and MERGE FindingObservation nodes; return list of detection_ids."""
    if not findings:
        return []
    try:
        result = session.run(_CREATE_FINDINGS_BATCH, findings=findings)
        return [record["detection_id"] for record in result]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def get_finding(session: Session, detection_id: str) -> dict | None:
    """Return a single FindingObservation by detection_id, or None."""
    try:
        result = session.run(_GET_FINDING, detection_id=detection_id)
        record = result.single()
        return dict(record["finding"]) if record else None
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def list_findings_for_scan(session: Session, scan_id: str) -> list[dict]:
    """Return all FindingObservation nodes for a given scan_id."""
    try:
        result = session.run(_LIST_FINDINGS_FOR_SCAN, scan_id=scan_id)
        return [dict(record["finding"]) for record in result]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def get_finding_history(
    session: Session,
    detection_id: str,
    radius_m: float = 500,
) -> list[dict]:
    """Return nearby FindingObservation nodes across all scans within radius_m metres."""
    try:
        result = session.run(
            _GET_FINDING_HISTORY,
            detection_id=detection_id,
            radius_m=radius_m,
        )
        return [
            {**dict(record["finding"]), "distance_m": record["distance_m"]}
            for record in result
        ]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def find_in_radius(
    session: Session,
    lat: float,
    lon: float,
    radius_m: float,
    limit: int = 20,
) -> list[dict]:
    """Return FindingObservation nodes within radius_m metres of (lat, lon)."""
    try:
        result = session.run(
            _FIND_IN_RADIUS,
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            limit=limit,
        )
        return [
            {**dict(record["finding"]), "distance_m": record["distance_m"]}
            for record in result
        ]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def find_in_bbox(
    session: Session,
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    limit: int = 20,
) -> list[dict]:
    """Return FindingObservation nodes within a bounding box."""
    try:
        result = session.run(
            _FIND_IN_BBOX,
            min_lat=min_lat,
            min_lon=min_lon,
            max_lat=max_lat,
            max_lon=max_lon,
            limit=limit,
        )
        return [dict(record["finding"]) for record in result]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc
