"""
Region repository — parameterized Cypher only, no f-string injection.
"""
from __future__ import annotations

from neo4j import Session
from neo4j.exceptions import ServiceUnavailable, TransientError

# ---------------------------------------------------------------------------
# Cypher constants
# ---------------------------------------------------------------------------

_MERGE_REGION = """
MERGE (r:MonitoringRegion {region_id: $region_id})
ON CREATE SET
    r.name        = $name,
    r.description = $description,
    r.bbox        = $bbox,
    r.created_at  = $created_at
ON MATCH SET
    r.name        = coalesce($name, r.name),
    r.description = coalesce($description, r.description)
RETURN r.region_id AS region_id
"""

_GET_REGION = """
MATCH (r:MonitoringRegion {region_id: $region_id})
RETURN r {.*} AS region
"""

_GET_REGION_GRAPH = """
MATCH (r:MonitoringRegion {region_id: $region_id})
OPTIONAL MATCH (r)-[:HAS_SCAN]->(s:Scan)
WITH r, s ORDER BY s.created_at DESC LIMIT 10
OPTIONAL MATCH (s)-[:PRODUCED]->(fo:FindingObservation)
RETURN
    r  {.*}                                      AS region,
    collect(DISTINCT s  {.*})                    AS scans,
    collect(DISTINCT fo {.*})                    AS findings
"""


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------

def merge_region(session: Session, region_data: dict) -> str:
    """MERGE a MonitoringRegion node and return its region_id."""
    try:
        result = session.run(
            _MERGE_REGION,
            region_id=region_data.get("region_id", ""),
            name=region_data.get("name"),
            description=region_data.get("description"),
            bbox=region_data.get("bbox"),
            created_at=region_data.get("created_at"),
        )
        record = result.single()
        return record["region_id"]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def get_region(session: Session, region_id: str) -> dict | None:
    """Return a single MonitoringRegion by region_id, or None."""
    try:
        result = session.run(_GET_REGION, region_id=region_id)
        record = result.single()
        return dict(record["region"]) if record else None
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def get_region_graph(session: Session, region_id: str) -> dict:
    """
    Return a subgraph dict with the region, its recent scans, and
    the findings produced by those scans.
    """
    try:
        result = session.run(_GET_REGION_GRAPH, region_id=region_id)
        record = result.single()
        if record is None:
            return {"region": None, "scans": [], "findings": []}
        return {
            "region": dict(record["region"]) if record["region"] else None,
            "scans": [dict(s) for s in record["scans"] if s],
            "findings": [dict(f) for f in record["findings"] if f],
        }
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc
