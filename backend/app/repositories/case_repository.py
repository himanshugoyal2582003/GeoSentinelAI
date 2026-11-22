"""
Case repository — parameterized Cypher only, no f-string injection.
"""
from __future__ import annotations

from neo4j import Session
from neo4j.exceptions import ServiceUnavailable, TransientError

# ---------------------------------------------------------------------------
# Cypher constants
# ---------------------------------------------------------------------------

_CREATE_CASE = """
MERGE (ic:InvestigationCase {case_id: $case_id})
ON CREATE SET
    ic.title         = $title,
    ic.status        = $status,
    ic.review_status = $review_status,
    ic.description   = $description,
    ic.created_at    = $created_at,
    ic.updated_at    = $updated_at
RETURN ic.case_id AS case_id
"""

_GET_CASE = """
MATCH (ic:InvestigationCase {case_id: $case_id})
RETURN ic {.*} AS case
"""

_LIST_CASES = """
MATCH (ic:InvestigationCase)
RETURN ic {.*} AS case
ORDER BY ic.created_at DESC
SKIP $offset
LIMIT $limit
"""

# MERGE prevents duplicates; we return whether the relationship was created.
_ADD_OBSERVATION_TO_CASE = """
MATCH (ic:InvestigationCase {case_id: $case_id})
MATCH (fo:FindingObservation {detection_id: $detection_id})
OPTIONAL MATCH (ic)-[r:HAS_OBSERVATION]->(fo)
WITH ic, fo, r
WHERE r IS NULL
MERGE (ic)-[rel:HAS_OBSERVATION]->(fo)
RETURN rel IS NOT NULL AS added
"""

_LIST_OBSERVATIONS_FOR_CASE = """
MATCH (ic:InvestigationCase {case_id: $case_id})-[:HAS_OBSERVATION]->(fo:FindingObservation)
RETURN fo {.*} AS finding
ORDER BY fo.created_at DESC
"""


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------

def create_case(session: Session, case_data: dict) -> str:
    """MERGE an InvestigationCase node and return its case_id."""
    try:
        result = session.run(
            _CREATE_CASE,
            case_id=case_data.get("case_id", ""),
            title=case_data.get("title"),
            status=case_data.get("status", "open"),
            review_status=case_data.get("review_status", "pending"),
            description=case_data.get("description"),
            created_at=case_data.get("created_at"),
            updated_at=case_data.get("updated_at"),
        )
        record = result.single()
        return record["case_id"]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def get_case(session: Session, case_id: str) -> dict | None:
    """Return a single InvestigationCase by case_id, or None."""
    try:
        result = session.run(_GET_CASE, case_id=case_id)
        record = result.single()
        return dict(record["case"]) if record else None
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def list_cases(session: Session, limit: int = 50, offset: int = 0) -> list[dict]:
    """Return a paginated list of InvestigationCase nodes."""
    try:
        result = session.run(_LIST_CASES, limit=limit, offset=offset)
        return [dict(record["case"]) for record in result]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def add_observation_to_case(
    session: Session, case_id: str, detection_id: str
) -> bool:
    """
    Link a FindingObservation to an InvestigationCase.
    Returns True if the relationship was freshly created, False if it existed.
    """
    try:
        result = session.run(
            _ADD_OBSERVATION_TO_CASE,
            case_id=case_id,
            detection_id=detection_id,
        )
        record = result.single()
        # If neither node matched the MERGE branch returned nothing, record is None.
        return bool(record["added"]) if record else False
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def list_observations_for_case(session: Session, case_id: str) -> list[dict]:
    """Return all FindingObservation nodes linked to an InvestigationCase."""
    try:
        result = session.run(_LIST_OBSERVATIONS_FOR_CASE, case_id=case_id)
        return [dict(record["finding"]) for record in result]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def update_case(
    session: Session,
    case_id: str,
    status: str | None = None,
    review_status: str | None = None,
    description: str | None = None,
    updated_at: str | None = None,
) -> dict | None:
    """Update fields on an InvestigationCase node."""
    query = """
    MATCH (c:InvestigationCase {case_id: $case_id})
    SET c.updated_at = $updated_at
    SET c.status = coalesce($status, c.status)
    SET c.review_status = coalesce($review_status, c.review_status)
    SET c.description = coalesce($description, c.description)
    RETURN c {.*} AS updated_case
    """
    try:
        result = session.run(
            query,
            case_id=case_id,
            status=status,
            review_status=review_status,
            description=description,
            updated_at=updated_at,
        )
        record = result.single()
        return dict(record["updated_case"]) if record else None
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc
