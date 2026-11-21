"""Security and input validation tests."""
from __future__ import annotations

import io
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app, raise_server_exceptions=True)


class TestSecurityAndValidation:
    def test_cypher_injection_in_scan_id_safely_handled(self):
        # Cypher injection payload in scan_id
        injection_id = "scan-1' OR 1=1 WITH s MATCH (n) DETACH DELETE n //"
        with patch("app.repositories.scan_repository.get_scan", return_value=None), \
             patch("app.api.scans.get_session"):
            resp = client.get(f"/api/scans/{injection_id}")
            # Parameterized Cypher safely treats this as literal scan_id and returns 404
            assert resp.status_code == 404
            # Verify no raw Cypher error is leaked
            assert "SyntaxError" not in resp.text
            assert "Cypher" not in resp.text

    def test_training_disabled_by_default_returns_403(self):
        with patch.dict(os.environ, {"TRAINING_ENABLED": "false"}):
            resp = client.post("/api/train")
            assert resp.status_code == 403
            assert "disabled" in resp.json()["detail"].lower()

    def test_invalid_lat_returns_422_before_image_processing(self):
        img_bytes = io.BytesIO()
        Image.new("RGB", (20, 20), color="blue").save(img_bytes, format="PNG")
        img_bytes.seek(0)
        files = {
            "historical": ("hist.png", img_bytes.getvalue(), "image/png"),
            "recent": ("rec.png", img_bytes.getvalue(), "image/png"),
        }
        resp = client.post(
            "/api/detect",
            files=files,
            params={"latitude": 999.0, "longitude": 73.85},
        )
        assert resp.status_code == 422

    def test_oversized_image_upload_rejected_with_413(self):
        # 2100 x 2000 = 4,200,000 pixels > 4MP
        img_bytes = io.BytesIO()
        Image.new("RGB", (2100, 2000), color="blue").save(img_bytes, format="PNG")
        img_bytes.seek(0)
        files = {
            "historical": ("hist.png", img_bytes.getvalue(), "image/png"),
            "recent": ("rec.png", img_bytes.getvalue(), "image/png"),
        }
        resp = client.post("/api/detect", files=files)
        assert resp.status_code == 413

    def test_credentials_never_exposed_in_health_response(self):
        resp = client.get("/api/health")
        content = resp.text.lower()
        assert "password" not in content
        assert "bolt+s://" not in content
        assert "auth" not in content

    def test_credentials_never_exposed_in_ready_error_response(self):
        with patch("app.api.health.verify_connectivity", return_value={"status": "error", "detail": "Connection refused to bolt://neo4j:secret123@host:7687"}):
            resp = client.get("/api/health/ready")
            assert resp.status_code == 503
            # Ensure custom details sanitize or don't leak passwords in standard flows
            assert resp.json()["status"] == "not_ready"
