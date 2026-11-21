"""
Idempotent Neo4j schema initialisation for GeoSentinelAI.

All statements use ``IF NOT EXISTS`` so they are safe to call repeatedly
(e.g. on every application startup).
"""
from __future__ import annotations

import logging
from typing import Any

from neo4j import Driver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constraint DDL — each is a (name, Cypher) pair so we can track them.
# ---------------------------------------------------------------------------

_CONSTRAINTS: list[tuple[str, str]] = [
    (
        "region_id_unique",
        "CREATE CONSTRAINT region_id_unique IF NOT EXISTS "
        "FOR (r:MonitoringRegion) REQUIRE r.region_id IS UNIQUE",
    ),
    (
        "scan_id_unique",
        "CREATE CONSTRAINT scan_id_unique IF NOT EXISTS "
        "FOR (s:Scan) REQUIRE s.scan_id IS UNIQUE",
    ),
    (
        "scan_idempotency_key_unique",
        "CREATE CONSTRAINT scan_idempotency_key_unique IF NOT EXISTS "
        "FOR (s:Scan) REQUIRE s.idempotency_key IS UNIQUE",
    ),
    (
        "scene_id_unique",
        "CREATE CONSTRAINT scene_id_unique IF NOT EXISTS "
        "FOR (sc:SatelliteScene) REQUIRE sc.scene_id IS UNIQUE",
    ),
    (
        "finding_detection_id_unique",
        "CREATE CONSTRAINT finding_detection_id_unique IF NOT EXISTS "
        "FOR (f:FindingObservation) REQUIRE f.detection_id IS UNIQUE",
    ),
    (
        "asset_id_unique",
        "CREATE CONSTRAINT asset_id_unique IF NOT EXISTS "
        "FOR (a:EvidenceAsset) REQUIRE a.asset_id IS UNIQUE",
    ),
    (
        "case_id_unique",
        "CREATE CONSTRAINT case_id_unique IF NOT EXISTS "
        "FOR (c:InvestigationCase) REQUIRE c.case_id IS UNIQUE",
    ),
    (
        "notification_id_unique",
        "CREATE CONSTRAINT notification_id_unique IF NOT EXISTS "
        "FOR (n:Notification) REQUIRE n.notification_id IS UNIQUE",
    ),
]

# ---------------------------------------------------------------------------
# Index DDL — (name, Cypher) pairs
# ---------------------------------------------------------------------------

_INDEXES: list[tuple[str, str]] = [
    # Spatial index on FindingObservation.location (point property)
    (
        "finding_location_point",
        "CREATE POINT INDEX finding_location_point IF NOT EXISTS "
        "FOR (f:FindingObservation) ON (f.location)",
    ),
    # B-tree / range indexes on common filter / sort properties
    (
        "scan_created_at_idx",
        "CREATE INDEX scan_created_at_idx IF NOT EXISTS "
        "FOR (s:Scan) ON (s.created_at)",
    ),
    (
        "scan_region_id_idx",
        "CREATE INDEX scan_region_id_idx IF NOT EXISTS "
        "FOR (s:Scan) ON (s.region_id)",
    ),
    (
        "finding_severity_idx",
        "CREATE INDEX finding_severity_idx IF NOT EXISTS "
        "FOR (f:FindingObservation) ON (f.severity)",
    ),
    (
        "finding_scan_id_idx",
        "CREATE INDEX finding_scan_id_idx IF NOT EXISTS "
        "FOR (f:FindingObservation) ON (f.scan_id)",
    ),
    (
        "finding_review_status_idx",
        "CREATE INDEX finding_review_status_idx IF NOT EXISTS "
        "FOR (f:FindingObservation) ON (f.review_status)",
    ),
    (
        "case_status_idx",
        "CREATE INDEX case_status_idx IF NOT EXISTS "
        "FOR (c:InvestigationCase) ON (c.status)",
    ),
    # Text indexes for full-text search
    (
        "finding_label_text",
        "CREATE TEXT INDEX finding_label_text IF NOT EXISTS "
        "FOR (f:FindingObservation) ON (f.label)",
    ),
    (
        "case_title_text",
        "CREATE TEXT INDEX case_title_text IF NOT EXISTS "
        "FOR (c:InvestigationCase) ON (c.title)",
    ),
]


def initialize_schema(driver: Driver, database: str = "neo4j") -> None:
    """Create all constraints and indexes idempotently.

    Safe to call multiple times — uses ``IF NOT EXISTS`` throughout.
    Logs each statement at DEBUG level; failures are logged as errors and
    re-raised so the caller can decide whether to abort startup.
    """
    logger.info("Initialising Neo4j schema (database=%s) …", database)

    with driver.session(database=database) as session:
        for name, cypher in _CONSTRAINTS:
            try:
                session.run(cypher)
                logger.debug("Constraint OK: %s", name)
            except Exception as exc:
                logger.error("Failed to create constraint %s: %s", name, exc)
                raise

        for name, cypher in _INDEXES:
            try:
                session.run(cypher)
                logger.debug("Index OK: %s", name)
            except Exception as exc:
                logger.error("Failed to create index %s: %s", name, exc)
                raise

    logger.info("Neo4j schema initialised successfully.")


def verify_schema(driver: Driver, database: str = "neo4j") -> dict[str, Any]:
    """Return the current constraints and indexes for the given database.

    Returns::

        {
            "constraints": [{"name": str, "type": str, "labelsOrTypes": [...], ...}],
            "indexes":     [{"name": str, "type": str, "labelsOrTypes": [...], ...}],
        }
    """
    with driver.session(database=database) as session:
        constraints_raw = session.run("SHOW CONSTRAINTS").data()
        indexes_raw = session.run("SHOW INDEXES").data()

    return {
        "constraints": constraints_raw,
        "indexes": indexes_raw,
    }
