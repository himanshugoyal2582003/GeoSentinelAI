"""API tests for /api/findings endpoints."""
from __future__ import annotations

from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=True)


class TestFindingsEndpoints:
    def test_get_finding_found(self):
        mock_finding = {
            "detection_id": "det-123",
            "original_finding_id": "GS-001",
            "confidence": 0.85,
            "latitude": 18.52,
            "longitude": 73.86,
        }
        with patch("app.repositories.finding_repository.get_finding", return_value=mock_finding), \
             patch("app.api.findings.get_session"):
            resp = client.get("/api/findings/det-123")
            assert resp.status_code == 200
            assert resp.json()["detection_id"] == "det-123"

    def test_get_finding_not_found(self):
        with patch("app.repositories.finding_repository.get_finding", return_value=None), \
             patch("app.api.findings.get_session"):
            resp = client.get("/api/findings/det-nonexistent")
            assert resp.status_code == 404

    def test_get_finding_history(self):
        mock_history = [
            {"detection_id": "det-older", "distance_m": 45.2, "confidence": 0.8},
        ]
        with patch("app.repositories.finding_repository.get_finding_history", return_value=mock_history), \
             patch("app.api.findings.get_session"):
            resp = client.get("/api/findings/det-123/history?radius_m=300")
            assert resp.status_code == 200
            data = resp.json()
            assert data["detection_id"] == "det-123"
            assert len(data["related_observations"]) == 1
            assert data["related_observations"][0]["distance_m"] == 45.2
