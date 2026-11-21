"""API tests for /api/health and /api/health/ready endpoints."""
from __future__ import annotations

from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=True)


class TestHealthEndpoints:
    def test_health_liveness_always_200(self):
        with patch("app.api.health.verify_connectivity", return_value={"status": "ok", "database": "neo4j"}):
            resp = client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["service"] == "geosentinel-api"
            assert data["neo4j"] == "connected"
            assert "model" in data

    def test_health_liveness_when_neo4j_down(self):
        with patch("app.api.health.verify_connectivity", return_value={"status": "error", "error": "service_unavailable"}):
            resp = client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["neo4j"] == "unavailable"

    def test_readiness_probe_200_when_connected(self):
        with patch("app.api.health.verify_connectivity", return_value={"status": "ok", "database": "neo4j"}):
            resp = client.get("/api/health/ready")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ready"
            assert data["database"] == "connected"

    def test_readiness_probe_503_when_unavailable(self):
        with patch("app.api.health.verify_connectivity", return_value={"status": "error", "detail": "Connection refused"}):
            resp = client.get("/api/health/ready")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "not_ready"
            assert data["database"] == "unavailable"

    def test_correlation_id_header_present(self):
        resp = client.get("/api/health")
        assert "X-Request-ID" in resp.headers
