"""API tests for /api/scans endpoints."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=True)


class TestScansEndpoints:
    def test_list_scans_from_neo4j(self):
        mock_scans = [
            {"scan_id": "scan-1", "created_at": "2025-01-01T00:00:00Z", "finding_count": 2},
            {"scan_id": "scan-2", "created_at": "2025-01-02T00:00:00Z", "finding_count": 0},
        ]
        with patch("app.repositories.scan_repository.list_scans", return_value=mock_scans), \
             patch("app.repositories.scan_repository.count_scans", return_value=2), \
             patch("app.api.scans.get_session"):
            resp = client.get("/api/scans?limit=10&offset=0")
            assert resp.status_code == 200
            data = resp.json()
            assert "scans" in data
            assert len(data["scans"]) == 2
            assert data["scans"][0]["scan_id"] == "scan-1"

    def test_list_scans_fallback_to_csv_on_db_error(self):
        with patch("app.api.scans.get_session", side_effect=Exception("Database down")), \
             patch("app.api.scans._csv_read_scans", return_value=[{"scan_id": "csv-scan-1"}]):
            resp = client.get("/api/scans")
            assert resp.status_code == 200
            data = resp.json()
            assert "scans" in data
            assert len(data["scans"]) == 1
            assert data["scans"][0]["scan_id"] == "csv-scan-1"

    def test_get_scan_by_id_found(self):
        mock_scan = {"scan_id": "scan-123", "mode": "live-sentinel2", "finding_count": 3}
        with patch("app.repositories.scan_repository.get_scan", return_value=mock_scan), \
             patch("app.api.scans.get_session"):
            resp = client.get("/api/scans/scan-123")
            assert resp.status_code == 200
            assert resp.json()["scan_id"] == "scan-123"

    def test_get_scan_by_id_not_found_returns_404(self):
        with patch("app.repositories.scan_repository.get_scan", return_value=None), \
             patch("app.api.scans.get_session"):
            resp = client.get("/api/scans/scan-nonexistent")
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"].lower()
