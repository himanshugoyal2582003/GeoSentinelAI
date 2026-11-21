"""API tests for /api/investigations endpoints."""
from __future__ import annotations

from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=True)


class TestInvestigationsEndpoints:
    def test_create_investigation(self):
        mock_case = {
            "case_id": "case-001",
            "title": "Quarry Site Alpha",
            "status": "open",
            "review_status": "pending",
        }
        with patch("app.services.investigation_service.create_investigation", return_value=mock_case), \
             patch("app.api.investigations.get_driver"):
            resp = client.post(
                "/api/investigations",
                json={"title": "Quarry Site Alpha", "description": "Investigating land changes"},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["case_id"] == "case-001"
            assert data["title"] == "Quarry Site Alpha"

    def test_get_investigation_found(self):
        mock_case = {
            "case_id": "case-001",
            "title": "Quarry Site Alpha",
            "observations": [{"detection_id": "det-1"}],
        }
        with patch("app.services.investigation_service.get_investigation", return_value=mock_case), \
             patch("app.api.investigations.get_driver"):
            resp = client.get("/api/investigations/case-001")
            assert resp.status_code == 200
            assert resp.json()["case_id"] == "case-001"

    def test_get_investigation_not_found(self):
        with patch("app.services.investigation_service.get_investigation", return_value=None), \
             patch("app.api.investigations.get_driver"):
            resp = client.get("/api/investigations/case-missing")
            assert resp.status_code == 404

    def test_associate_observation(self):
        mock_res = {
            "case_id": "case-001",
            "detection_id": "det-001",
            "created": True,
            "message": "Observation linked to case.",
        }
        with patch("app.services.investigation_service.add_observation_to_case", return_value=mock_res), \
             patch("app.api.investigations.get_driver"):
            resp = client.post(
                "/api/investigations/case-001/observations",
                json={"detection_id": "det-001"},
            )
            assert resp.status_code == 200
            assert resp.json()["created"] is True
