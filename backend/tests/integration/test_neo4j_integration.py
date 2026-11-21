"""Integration tests executing against a real Neo4j database instance.

Skipped automatically when NEO4J_TEST_URI is not configured in the environment.
NEVER runs against production databases.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


def _skip_if_no_neo4j():
    if not os.getenv("NEO4J_TEST_URI"):
        pytest.skip("NEO4J_TEST_URI not set — skipping real Neo4j integration test.")


class TestNeo4jRealIntegration:
    def test_connectivity_and_schema_init(self, neo4j_test_driver):
        _skip_if_no_neo4j()
        driver, db = neo4j_test_driver
        from app.db.schema import initialize_schema, verify_schema

        # 1. First run
        initialize_schema(driver, db)
        info = verify_schema(driver, db)
        assert len(info["constraints"]) >= 5

        # 2. Repeated run must be idempotent
        initialize_schema(driver, db)
        info2 = verify_schema(driver, db)
        assert len(info2["constraints"]) == len(info["constraints"])

    def test_scan_id_unique_constraint_enforced(self, neo4j_test_session):
        _skip_if_no_neo4j()
        session = neo4j_test_session
        scan_id = f"test-scan-{uuid4().hex}"

        # Insert first
        session.run("CREATE (s:Scan {scan_id: $sid})", sid=scan_id).consume()

        # Insert duplicate must raise ClientError
        from neo4j.exceptions import ClientError
        with pytest.raises(ClientError):
            session.run("CREATE (s:Scan {scan_id: $sid})", sid=scan_id).consume()

    def test_same_coordinates_produce_separate_observations(self, neo4j_test_session):
        _skip_if_no_neo4j()
        session = neo4j_test_session
        det1 = f"det-1-{uuid4().hex}"
        det2 = f"det-2-{uuid4().hex}"

        # Two observations at exact same coordinates across different scans
        lat, lon = 18.5204, 73.8567
        session.run(
            "MERGE (f:FindingObservation {detection_id: $did}) "
            "ON CREATE SET f.latitude = $lat, f.longitude = $lon, "
            "f.location = point({latitude: $lat, longitude: $lon, crs: 'WGS-84'})",
            did=det1, lat=lat, lon=lon,
        ).consume()
        session.run(
            "MERGE (f:FindingObservation {detection_id: $did}) "
            "ON CREATE SET f.latitude = $lat, f.longitude = $lon, "
            "f.location = point({latitude: $lat, longitude: $lon, crs: 'WGS-84'})",
            did=det2, lat=lat, lon=lon,
        ).consume()

        res = session.run(
            "MATCH (f:FindingObservation) WHERE f.detection_id IN [$d1, $d2] RETURN count(f) AS cnt",
            d1=det1, d2=det2,
        ).single()
        assert res["cnt"] == 2  # Kept strictly distinct

    def test_unicode_metadata_preserved_in_graph(self, neo4j_test_session):
        _skip_if_no_neo4j()
        session = neo4j_test_session
        reg_id = f"reg-unicode-{uuid4().hex}"
        unicode_name = "पुणे खाण परिसर 🔍"

        session.run(
            "MERGE (r:MonitoringRegion {region_id: $rid}) "
            "ON CREATE SET r.name = $name",
            rid=reg_id, name=unicode_name,
        ).consume()

        record = session.run(
            "MATCH (r:MonitoringRegion {region_id: $rid}) RETURN r.name AS name",
            rid=reg_id,
        ).single()
        assert record["name"] == unicode_name
