"""Investigation case management service for GeoSentinelAI.

Supports creating investigation cases, querying case details, and linking
finding observations to cases with duplicate prevention.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from neo4j.exceptions import ServiceUnavailable, TransientError

logger = logging.getLogger(__name__)

_CREATE_CASE = """
MERGE (c:InvestigationCase {case_id: $case_id})
ON CREATE SET
    c.title         = $title,
    c.description   = $description,
    c.status        = $status,
    c.review_status = $review_status,
    c.created_at    = $created_at,
    c.updated_at    = $created_at
RETURN c {.*} AS case_data
"""

_GET_CASE = """
MATCH (c:InvestigationCase {case_id: $case_id})
OPTIONAL MATCH (c)-[:HAS_OBSERVATION]->(fo:FindingObservation)
RETURN c {.*} AS case_data, collect(fo {.*}) AS observations
"""

_LIST_CASES = """
MATCH (c:InvestigationCase)
OPTIONAL MATCH (c)-[:HAS_OBSERVATION]->(fo:FindingObservation)
RETURN c {.*} AS case_data, count(fo) AS observation_count
ORDER BY c.created_at DESC
SKIP $offset LIMIT $limit
"""

_ADD_OBSERVATION = """
MATCH (c:InvestigationCase {case_id: $case_id})
MATCH (fo:FindingObservation {detection_id: $detection_id})
MERGE (c)-[r:HAS_OBSERVATION]->(fo)
ON CREATE SET r.associated_at = $now, r.is_new = true
ON MATCH SET r.is_new = false
RETURN r.is_new AS is_new
"""


def create_investigation(
    driver: Any,
    title: str,
    description: str | None = None,
    status: str = "open",
    review_status: str = "pending",
) -> dict[str, Any]:
    """Create a new InvestigationCase node."""
    case_id = f"case-{uuid4().hex}"
    now = datetime.now(timezone.utc).isoformat()
    try:
        with driver.session() as session:
            result = session.run(
                _CREATE_CASE,
                case_id=case_id,
                title=title,
                description=description or "",
                status=status,
                review_status=review_status,
                created_at=now,
            )
            record = result.single()
            return dict(record["case_data"])
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable.") from exc


def get_investigation(driver: Any, case_id: str) -> dict[str, Any] | None:
    """Get an InvestigationCase and its associated observations."""
    try:
        with driver.session() as session:
            result = session.run(_GET_CASE, case_id=case_id)
            record = result.single()
            if not record or not record.get("case_data"):
                return None
            case_data = dict(record["case_data"])
            case_data["observations"] = [dict(o) for o in record["observations"] if o]
            return case_data
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable.") from exc


def list_investigations(
    driver: Any,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List investigation cases with observation counts."""
    try:
        with driver.session() as session:
            result = session.run(_LIST_CASES, limit=limit, offset=offset)
            cases = []
            for record in result:
                item = dict(record["case_data"])
                item["observation_count"] = record["observation_count"]
                cases.append(item)
            return cases
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable.") from exc


def add_observation_to_case(
    driver: Any,
    case_id: str,
    detection_id: str,
) -> dict[str, Any]:
    """Link a finding observation to a case, preventing duplicates."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        with driver.session() as session:
            result = session.run(
                _ADD_OBSERVATION,
                case_id=case_id,
                detection_id=detection_id,
                now=now,
            )
            record = result.single()
            if not record:
                raise ValueError("Case or finding observation not found.")
            return {
                "case_id": case_id,
                "detection_id": detection_id,
                "created": bool(record["is_new"]),
                "message": "Observation linked to case." if record["is_new"] else "Observation already linked.",
            }
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable.") from exc


def update_investigation(
    driver: Any,
    case_id: str,
    status: str | None = None,
    review_status: str | None = None,
    description: str | None = None,
) -> dict[str, Any] | None:
    """Update case status, review_status, or description."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        with driver.session() as session:
            from app.repositories import case_repository
            return case_repository.update_case(
                session,
                case_id=case_id,
                status=status,
                review_status=review_status,
                description=description,
                updated_at=now,
            )
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable.") from exc
