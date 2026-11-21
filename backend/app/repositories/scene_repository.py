"""
Scene repository — parameterized Cypher only, no f-string injection.
"""
from __future__ import annotations

from neo4j import Session
from neo4j.exceptions import ServiceUnavailable, TransientError

# ---------------------------------------------------------------------------
# Cypher constants
# ---------------------------------------------------------------------------

_MERGE_SCENE = """
MERGE (sc:SatelliteScene {scene_id: $scene_id})
ON CREATE SET
    sc.provider        = $provider,
    sc.acquired_at     = $acquired_at,
    sc.cloud_cover     = $cloud_cover,
    sc.asset_metadata  = $asset_metadata,
    sc.created_at      = $created_at
RETURN sc.scene_id AS scene_id
"""

_GET_SCENE = """
MATCH (sc:SatelliteScene {scene_id: $scene_id})
RETURN sc {.*} AS scene
"""

_LIST_SCENES_FOR_SCAN = """
MATCH (s:Scan {scan_id: $scan_id})-[:USED_SCENE]->(sc:SatelliteScene)
RETURN sc {.*} AS scene
ORDER BY sc.acquired_at DESC
"""


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------

def merge_scene(session: Session, scene_data: dict) -> str:
    """MERGE a SatelliteScene node and return scene_id."""
    try:
        result = session.run(
            _MERGE_SCENE,
            scene_id=scene_data.get("scene_id", ""),
            provider=scene_data.get("provider"),
            acquired_at=scene_data.get("acquired_at"),
            cloud_cover=scene_data.get("cloud_cover"),
            asset_metadata=scene_data.get("asset_metadata"),
            created_at=scene_data.get("created_at"),
        )
        record = result.single()
        return record["scene_id"]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def get_scene(session: Session, scene_id: str) -> dict | None:
    """Return a single SatelliteScene by scene_id, or None."""
    try:
        result = session.run(_GET_SCENE, scene_id=scene_id)
        record = result.single()
        return dict(record["scene"]) if record else None
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc


def list_scenes_for_scan(session: Session, scan_id: str) -> list[dict]:
    """Return all SatelliteScene nodes linked to a Scan via USED_SCENE."""
    try:
        result = session.run(_LIST_SCENES_FOR_SCAN, scan_id=scan_id)
        return [dict(record["scene"]) for record in result]
    except (ServiceUnavailable, TransientError) as exc:
        raise RuntimeError("Neo4j is temporarily unavailable. Please retry.") from exc
