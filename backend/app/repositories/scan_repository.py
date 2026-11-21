"""
Scan repository — parameterized Cypher only, no f-string injection.
"""
from __future__ import annotations

from neo4j import Session
from neo4j.exceptions import ServiceUnavailable, TransientError

# ---------------------------------------------------------------------------
# Cypher constants (never built from user data)
# ---------------------------------------------------------------------------

_MERGE_SCAN = """
MERGE (s:Scan {scan_id: $scan_id})
ON CREATE SET
    s.idempotency_key  = $idempotency_key,
    s.region_id        = $region_id,
    s.mode             = $mode,
    s.status           = $status,
    s.historical_date  = $historical_date,
    s.recent_date      = $recent_date,
    s.changed_area_sqm = $changed_area_sqm,
    s.finding_count    = $finding_count,
    s.model_name       = $model_name,
    s.created_at       = $created_at,
    s.processing_metadata = $processing_metadata,
    s.summary          = $summary,
    s.source_metadata  = $source_metadata
RETURN s.scan_id AS scan_id
"""

_GET_SCAN = """
MATCH (s:Scan {scan_id: $scan_id})
RETURN s {.*} AS scan
"""

_LIST_SCANS_ALL = """
MATCH (s:Scan)
RETURN s {.*} AS scan
ORDER BY s.created_at DESC
SKIP $offset
LIMIT $limit
"""

_LIST_SCANS_BY_REGION = """
MATCH (s:Scan {region_id: $region_id})
RETURN s {.*} AS scan
ORDER BY s.created_at DESC
SKIP $offset
LIMIT $limit
"""

_GET_SCAN_BY_IDEMPOTENCY_KEY = """
MATCH (s:Scan {idempotency_key: $idempotency_key})
RETURN s {.*} AS scan
"""

_UPDATE_SCAN_STATUS = """
MATCH (s:Scan {scan_id: $scan_id})
SET s.status = $status
"""

_COUNT_SCANS_ALL = """
MATCH (s:Scan)
RETURN count(s) AS total
"""

_COUNT_SCANS_BY_REGION = """
MATCH (s:Scan {region_id: $region_id})
RETURN count(s) AS total
"""


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------

def create_scan(session: Session, scan_data: dict) -> str:
    """MERGE a Scan node and return its scan_id."""
    try:
        result = session.run(
            _MERGE_SCAN,
            scan_id=scan_data.get("scan_id", ""),
            idempotency_key=scan_data.get("idempotency_key"),
            region_id=scan_data.get("region_id"),
            mode=scan_data.get("mode"),
            status=scan_data.get("status", "pending"),
            historical_date=scan_data.get("historical_date"),
            recent_date=scan_data.get("recent_date"),
            changed_area_sqm=scan_data.get("changed_area_sqm"),
            finding_count=scan_data.get("finding_count", 0),
            model_name=scan_data.get("model_name"),
            created_at=scan_data.get("created_at"),
            processing_metadata=scan_data.get("processing_metadata"),
            summary=scan_data.get("summary"),
            source_metadata=scan_data.get("source_metadata"),
        )
        record = result.single()
        return record["scan_id"]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def get_scan(session: Session, scan_id: str) -> dict | None:
    """Return a single Scan by scan_id, or None if not found."""
    try:
        result = session.run(_GET_SCAN, scan_id=scan_id)
        record = result.single()
        return dict(record["scan"]) if record else None
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def list_scans(
    session: Session,
    region_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return a paginated list of Scan nodes, optionally filtered by region_id."""
    try:
        if region_id is not None:
            result = session.run(
                _LIST_SCANS_BY_REGION,
                region_id=region_id,
                limit=limit,
                offset=offset,
            )
        else:
            result = session.run(_LIST_SCANS_ALL, limit=limit, offset=offset)
        return [dict(record["scan"]) for record in result]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def get_scan_by_idempotency_key(session: Session, key: str) -> dict | None:
    """Return a Scan whose idempotency_key matches, or None."""
    try:
        result = session.run(_GET_SCAN_BY_IDEMPOTENCY_KEY, idempotency_key=key)
        record = result.single()
        return dict(record["scan"]) if record else None
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def update_scan_status(session: Session, scan_id: str, status: str) -> None:
    """Update the status property of a Scan node."""
    try:
        session.run(_UPDATE_SCAN_STATUS, scan_id=scan_id, status=status)
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def count_scans(session: Session, region_id: str | None = None) -> int:
    """Return the total number of Scan nodes, optionally filtered by region."""
    try:
        if region_id is not None:
            result = session.run(_COUNT_SCANS_BY_REGION, region_id=region_id)
        else:
            result = session.run(_COUNT_SCANS_ALL)
        record = result.single()
        return record["total"] if record else 0
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc
