"""Investigation intelligence and graph analysis service for GeoSentinelAI.

Provides spatial and temporal association queries to assist human investigators.
Never automatically merges distinct observations or classifies sites as illegal mining.
"""
from __future__ import annotations

import logging
from typing import Any

from neo4j.exceptions import ServiceUnavailable, TransientError

logger = logging.getLogger(__name__)

_GET_REGION_HISTORY = """
MATCH (r:MonitoringRegion {region_id: $region_id})
OPTIONAL MATCH (r)-[:HAS_SCAN]->(s:Scan)
WITH r, s ORDER BY s.created_at DESC
SKIP $offset LIMIT $limit
RETURN r {.*} AS region, collect(s {.*}) AS scans
"""

_RECOMMEND_RELATED = """
MATCH (target:FindingObservation {detection_id: $detection_id})
MATCH (other:FindingObservation)
WHERE other.detection_id <> target.detection_id
  AND other.scan_id <> target.scan_id
  AND point.distance(
        point({latitude: target.latitude, longitude: target.longitude, crs: 'WGS-84'}),
        point({latitude: other.latitude, longitude: other.longitude, crs: 'WGS-84'})
      ) <= $radius_m
WITH target, other,
     point.distance(
        point({latitude: target.latitude, longitude: target.longitude, crs: 'WGS-84'}),
        point({latitude: other.latitude, longitude: other.longitude, crs: 'WGS-84'})
     ) AS distance_m
RETURN other {.*} AS observation,
       distance_m,
       "Requires human review: proximity candidate only, not verified same quarry" AS note
ORDER BY distance_m ASC
LIMIT $limit
"""


def get_region_scan_history(
    driver: Any,
    region_id: str,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Fetch scan history and region metadata from Neo4j."""
    try:
        with driver.session() as session:
            result = session.run(
                _GET_REGION_HISTORY,
                region_id=region_id,
                limit=limit,
                offset=offset,
            )
            record = result.single()
            if not record or not record.get("region"):
                return {"region": None, "scans": []}
            return {
                "region": dict(record["region"]),
                "scans": [dict(s) for s in record["scans"] if s],
            }
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable.") from exc


def recommend_related_observations(
    driver: Any,
    detection_id: str,
    radius_m: float = 500.0,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Recommend nearby observations across different scans for human investigator review.

    Observations remain strictly distinct; candidates are ranked by spatial distance.
    """
    try:
        with driver.session() as session:
            result = session.run(
                _RECOMMEND_RELATED,
                detection_id=detection_id,
                radius_m=radius_m,
                limit=limit,
            )
            candidates = []
            for record in result:
                obs = dict(record["observation"])
                obs["distance_m"] = round(float(record["distance_m"]), 1)
                obs["investigation_note"] = record["note"]
                candidates.append(obs)
            return candidates
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable.") from exc
