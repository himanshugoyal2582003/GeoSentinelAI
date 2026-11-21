"""
Evidence repository — parameterized Cypher only, no f-string injection.
"""
from __future__ import annotations

from neo4j import Session
from neo4j.exceptions import ServiceUnavailable, TransientError

# ---------------------------------------------------------------------------
# Cypher constants
# ---------------------------------------------------------------------------

_CREATE_EVIDENCE_ASSET = """
MERGE (ea:EvidenceAsset {asset_id: $asset_id})
ON CREATE SET
    ea.uri        = $uri,
    ea.sha256     = $sha256,
    ea.media_type = $media_type,
    ea.file_size  = $file_size,
    ea.asset_type = $asset_type,
    ea.created_at = $created_at
RETURN ea.asset_id AS asset_id
"""

_LINK_EVIDENCE_TO_FINDING = """
MATCH (fo:FindingObservation {detection_id: $detection_id})
MATCH (ea:EvidenceAsset {asset_id: $asset_id})
MERGE (fo)-[:SUPPORTED_BY]->(ea)
"""

_GET_EVIDENCE_FOR_FINDING = """
MATCH (fo:FindingObservation {detection_id: $detection_id})-[:SUPPORTED_BY]->(ea:EvidenceAsset)
RETURN ea {.*} AS asset
ORDER BY ea.created_at DESC
"""


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------

def create_evidence_asset(session: Session, asset_data: dict) -> str:
    """MERGE an EvidenceAsset node and return its asset_id."""
    try:
        result = session.run(
            _CREATE_EVIDENCE_ASSET,
            asset_id=asset_data.get("asset_id", ""),
            uri=asset_data.get("uri"),
            sha256=asset_data.get("sha256"),
            media_type=asset_data.get("media_type"),
            file_size=asset_data.get("file_size"),
            asset_type=asset_data.get("asset_type"),
            created_at=asset_data.get("created_at"),
        )
        record = result.single()
        return record["asset_id"]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def link_evidence_to_finding(
    session: Session, detection_id: str, asset_id: str
) -> None:
    """Create a SUPPORTED_BY relationship from FindingObservation to EvidenceAsset."""
    try:
        session.run(
            _LINK_EVIDENCE_TO_FINDING,
            detection_id=detection_id,
            asset_id=asset_id,
        )
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def get_evidence_for_finding(session: Session, detection_id: str) -> list[dict]:
    """Return all EvidenceAsset nodes linked to a FindingObservation."""
    try:
        result = session.run(_GET_EVIDENCE_FOR_FINDING, detection_id=detection_id)
        return [dict(record["asset"]) for record in result]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc
