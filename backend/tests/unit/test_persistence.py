"""Unit tests for persistence_service."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from app.services.persistence_service import persist_scan


def test_persist_scan_success(sample_scan_result, sample_source_metadata):
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    with patch("app.services.persistence_service._csv_save_scan"):
        scan_id = persist_scan(
            mock_driver,
            sample_scan_result,
            sample_source_metadata,
            mode="live-sentinel2",
        )

    assert scan_id.startswith("scan-")
    mock_session.execute_write.assert_called_once()


def test_persist_scan_idempotency_replay(sample_scan_result, sample_source_metadata):
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_session.run.return_value.single.return_value = {"sid": "scan-existing-123"}

    scan_id = persist_scan(
        mock_driver,
        sample_scan_result,
        sample_source_metadata,
        mode="live-sentinel2",
        idempotency_key="idemp-key-1",
    )
    assert scan_id == "scan-existing-123"
    # execute_write should NOT be called on replay
    mock_session.execute_write.assert_not_called()


def test_persist_scan_failure_raises_runtime_error(sample_scan_result, sample_source_metadata):
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_session.execute_write.side_effect = Exception("Neo4j database write failed")

    with pytest.raises(RuntimeError) as exc_info:
        persist_scan(
            mock_driver,
            sample_scan_result,
            sample_source_metadata,
            mode="live-sentinel2",
        )
    assert "Neo4j write failed" in str(exc_info.value)
