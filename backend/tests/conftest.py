"""
Shared pytest fixtures for GeoSentinelAI backend tests.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv

# Load backend/.env if present
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def prevent_real_neo4j_in_unit_tests(monkeypatch, request):
    """Prevent unit and API tests from waiting on real network connections when not testing integration."""
    if "integration" in request.keywords:
        return
    # Default verify_connectivity to return ok unless specifically overridden in test
    monkeypatch.setattr("app.db.neo4j.verify_connectivity", lambda: {"status": "ok", "database": "neo4j"})


# ---------------------------------------------------------------------------
# Neo4j mock fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> MagicMock:
    """A mock Neo4j session."""
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


@pytest.fixture
def mock_neo4j_driver(mock_session: MagicMock) -> MagicMock:
    """A mock Neo4j driver that returns mock_session from .session()."""
    driver = MagicMock()
    driver.session.return_value = mock_session
    driver.verify_connectivity.return_value = None
    return driver


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------


@pytest.fixture
def test_app(mock_neo4j_driver: MagicMock) -> TestClient:
    """FastAPI TestClient with Neo4j driver mocked out."""
    # Patch the driver singleton before importing app to avoid real connection
    with patch("app.db.neo4j._driver", mock_neo4j_driver):
        from app.main import app  # noqa: PLC0415
        client = TestClient(app, raise_server_exceptions=True)
        yield client


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_source_metadata() -> dict[str, Any]:
    return {
        "provider": "Microsoft Planetary Computer / Copernicus Sentinel-2 L2A",
        "bbox": [73.82, 18.48, 73.90, 18.56],
        "historicalItem": "S2B_MSIL2A_20250101T000000_N0511_R000_T43PBL_20250101T000000",
        "recentItem": "S2B_MSIL2A_20251001T000000_N0511_R000_T43PBL_20251001T000000",
        "historicalCloudCover": 2.3,
        "recentCloudCover": 1.8,
        "historicalImage": "/media/historical-live.png",
        "recentImage": "/media/recent-live.png",
        "sceneCount": 6,
        "sceneCadenceDays": 5,
        "note": "Public satellite imagery.",
    }


@pytest.fixture
def sample_finding() -> dict[str, Any]:
    return {
        "detection_id": "det-abc123",
        "original_finding_id": "GS-LIVE-001",
        "scan_id": "scan-20250101120000-aabbcc",
        "label": "Detected change 1",
        "severity": "high",
        "confidence": 0.87,
        "area_sqm": 15000,
        "latitude": 18.52,
        "longitude": 73.86,
        "first_observed": "2025-01-01",
        "last_observed": "2025-10-01",
        "change_type": "Spectral surface change",
        "model_score": 0.91,
        "detection_error_sqm": 500,
        "region_bbox": [18.48, 73.82, 18.56, 73.90],
        "review_status": "pending",
    }


@pytest.fixture
def sample_scan_result() -> dict[str, Any]:
    """Dict matching the shape returned by the live-detect / detect API endpoints."""
    return {
        "mode": "live-sentinel2",
        "region": "Pune quarry belt",
        "historicalDate": "2025-01-01",
        "recentDate": "2025-10-01",
        "findings": [
            {
                "id": "GS-LIVE-001",
                "label": "Detected change 1",
                "severity": "high",
                "confidence": 0.87,
                "areaSqm": 15000,
                "coordinates": [18.52, 73.86],
                "regionBbox": [18.48, 73.82, 18.56, 73.90],
                "detectionErrorSqm": 500,
                "googleMapsUrl": "https://www.google.com/maps/search/?api=1&query=18.520000,73.860000",
                "googleSatelliteUrl": "https://www.google.com/maps/@?api=1&map_action=map&center=18.520000,73.860000&zoom=17&basemap=satellite",
                "changeType": "Spectral surface change",
                "firstObserved": "2025-01-01",
                "lastObserved": "2025-10-01",
                "status": "Needs review",
                "modelScore": 0.91,
            }
        ],
        "summary": {
            "changedAreaSqm": 15000,
            "changedAreaHa": 1.5,
            "highRiskCount": 1,
            "averageConfidence": 0.87,
        },
        "timeline": [
            {"month": "2025-01-01", "areaSqm": 0},
            {"month": "2025-10-01", "areaSqm": 15000},
        ],
        "processing": {
            "threshold": 45.5,
            "components": 1,
            "model": "ChangeCNN",
            "cloudMaskPixels": 120,
            "alignmentShiftPixels": [0.1, -0.2],
            "seasonalNormalization": "per-channel percentile matching",
        },
        "source": {
            "provider": "Microsoft Planetary Computer / Copernicus Sentinel-2 L2A",
            "bbox": [73.82, 18.48, 73.90, 18.56],
            "historicalItem": "S2B_20250101",
            "recentItem": "S2B_20251001",
            "historicalCloudCover": 2.3,
            "recentCloudCover": 1.8,
            "historicalImage": "/media/historical-live.png",
            "recentImage": "/media/recent-live.png",
            "sceneCount": 6,
            "sceneCadenceDays": 5,
            "note": "Public satellite imagery.",
        },
        "scanId": "scan-20250101120000-aabbcc",
    }


# ---------------------------------------------------------------------------
# Real Neo4j integration fixtures (skipped when env vars not set)
# ---------------------------------------------------------------------------


def _neo4j_test_env() -> dict[str, str] | None:
    uri = os.getenv("NEO4J_TEST_URI")
    if not uri:
        return None
    return {
        "uri": uri,
        "username": os.getenv("NEO4J_TEST_USERNAME", "neo4j"),
        "password": os.getenv("NEO4J_TEST_PASSWORD", "neo4j"),
        "database": os.getenv("NEO4J_TEST_DATABASE", "neo4j"),
    }


@pytest.fixture
def neo4j_test_session():
    """A real Neo4j session for integration tests.

    Skipped automatically when NEO4J_TEST_URI is not set.
    """
    env = _neo4j_test_env()
    if env is None:
        pytest.skip("NEO4J_TEST_URI not set — skipping integration test")

    from neo4j import GraphDatabase  # noqa: PLC0415

    driver = GraphDatabase.driver(env["uri"], auth=(env["username"], env["password"]))
    try:
        driver.verify_connectivity()
        with driver.session(database=env["database"]) as session:
            yield session
    finally:
        driver.close()


@pytest.fixture
def neo4j_test_driver():
    """A real Neo4j driver for integration tests.

    Skipped automatically when NEO4J_TEST_URI is not set.
    """
    env = _neo4j_test_env()
    if env is None:
        pytest.skip("NEO4J_TEST_URI not set — skipping integration test")

    from neo4j import GraphDatabase  # noqa: PLC0415

    driver = GraphDatabase.driver(env["uri"], auth=(env["username"], env["password"]))
    try:
        driver.verify_connectivity()
        yield driver, env["database"]
    finally:
        driver.close()
