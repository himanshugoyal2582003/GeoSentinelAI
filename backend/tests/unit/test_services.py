"""Unit tests for service layer (evidence_service, graph_service, investigation_service, persistence_service)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest

from app.services.evidence_service import LocalEvidenceStorage, register_image_asset
from app.services import graph_service, investigation_service


class TestEvidenceService:
    def test_local_storage_store_and_read(self, tmp_path: Path):
        storage = LocalEvidenceStorage(base_dir=tmp_path)
        data = b"fake-satellite-image-bytes-12345"
        uri, sha256_hex, size = storage.store_bytes(data, "diff.png")

        assert size == len(data)
        assert len(sha256_hex) == 64
        assert uri.startswith("/media/evidence/")

        # Verify read back
        retrieved = storage.read_bytes(uri)
        assert retrieved == data

    def test_local_storage_file_not_found(self, tmp_path: Path):
        storage = LocalEvidenceStorage(base_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            storage.read_bytes("/media/evidence/nonexistent.png")

    def test_register_image_asset(self, tmp_path: Path):
        storage = LocalEvidenceStorage(base_dir=tmp_path)
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        asset_id = register_image_asset(
            storage,
            mock_driver,
            detection_id="det-001",
            file_bytes=b"test-bytes",
            filename="test.png",
            asset_type="diff_image",
        )
        assert asset_id.startswith("asset-")
        mock_session.run.assert_called_once()


class TestGraphService:
    def test_get_region_scan_history_found(self):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        mock_record = {
            "region": {"region_id": "r1", "name": "Pune"},
            "scans": [{"scan_id": "s1"}],
        }
        mock_session.run.return_value.single.return_value = mock_record

        res = graph_service.get_region_scan_history(mock_driver, "r1")
        assert res["region"]["region_id"] == "r1"
        assert len(res["scans"]) == 1

    def test_get_region_scan_history_missing(self):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_session.run.return_value.single.return_value = None

        res = graph_service.get_region_scan_history(mock_driver, "r-missing")
        assert res["region"] is None
        assert res["scans"] == []

    def test_recommend_related_observations(self):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        mock_session.run.return_value = [
            {
                "observation": {"detection_id": "det-2", "confidence": 0.82},
                "distance_m": 125.4,
                "note": "Requires human review",
            }
        ]

        candidates = graph_service.recommend_related_observations(mock_driver, "det-1", radius_m=500.0)
        assert len(candidates) == 1
        assert candidates[0]["detection_id"] == "det-2"
        assert candidates[0]["distance_m"] == 125.4


class TestInvestigationService:
    def test_create_investigation(self):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        mock_case = {"case_id": "c1", "title": "Pit Survey", "status": "open"}
        mock_session.run.return_value.single.return_value = {"case_data": mock_case}

        res = investigation_service.create_investigation(mock_driver, title="Pit Survey")
        assert res["title"] == "Pit Survey"

    def test_get_investigation_found(self):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        mock_record = {
            "case_data": {"case_id": "c1", "title": "Pit Survey"},
            "observations": [{"detection_id": "det-1"}],
        }
        mock_session.run.return_value.single.return_value = mock_record

        res = investigation_service.get_investigation(mock_driver, "c1")
        assert res["case_id"] == "c1"
        assert len(res["observations"]) == 1

    def test_list_investigations(self):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        mock_session.run.return_value = [
            {"case_data": {"case_id": "c1"}, "observation_count": 2}
        ]

        res = investigation_service.list_investigations(mock_driver)
        assert len(res) == 1
        assert res[0]["observation_count"] == 2

    def test_add_observation_to_case_new(self):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_session.run.return_value.single.return_value = {"is_new": True}

        res = investigation_service.add_observation_to_case(mock_driver, "c1", "det-1")
        assert res["created"] is True
