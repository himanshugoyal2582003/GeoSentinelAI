from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import history
from app.services.persistence_service import persist_scan


def _result() -> tuple[dict, dict]:
    result = {
        "region": "Test quarry",
        "historicalDate": "2025-01-01",
        "recentDate": "2025-10-01",
        "summary": {"changedAreaSqm": 1500},
        "processing": {"model": "ChangeCNN", "cloudMaskFraction": 0.05},
        "findings": [{
            "id": "GS-TEST-001",
            "label": "Detected change",
            "areaName": "North wall",
            "changeType": "Surface change",
            "modelScore": 0.8,
            "detectionErrorSqm": 100,
            "coordinates": [18.52, 73.86],
            "areaSqm": 1500,
            "severity": "high",
            "confidence": 0.9,
            "firstObserved": "2025-01-01",
            "lastObserved": "2025-10-01",
            "regionBbox": [18.51, 73.85, 18.53, 73.87],
        }],
    }
    source = {
        "bbox": [73.82, 18.48, 73.90, 18.56],
        "imageCaptureId": "a" * 32,
        "resolutionMeters": 10,
    }
    return result, source


def test_csv_scan_round_trip_retains_report_data(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(history, "SCAN_FILE", tmp_path / "scans.csv")
    monkeypatch.setattr(history, "FINDING_FILE", tmp_path / "findings.csv")
    result, source = _result()

    scan_id = "scan-shared-id"
    assert history.save_scan(result, source, scan_id=scan_id) == scan_id
    scan = history.read_scan(scan_id)
    findings = history.read_findings_for_scan(scan_id)

    assert scan is not None
    assert json.loads(scan["source_metadata"]) == source
    assert json.loads(scan["processing_metadata"]) == result["processing"]
    assert findings[0]["original_finding_id"] == "GS-TEST-001"
    assert findings[0]["region_bbox"] == result["findings"][0]["regionBbox"]
    assert findings[0]["change_type"] == "Surface change"


def test_neo4j_csv_mirror_uses_the_same_scan_id() -> None:
    result, source = _result()
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session

    with (
        patch("app.services.persistence_service._csv_save_scan") as csv_save,
        patch("app.services.persistence_service.threading.Thread") as thread_class,
    ):
        scan_id = persist_scan(driver, result, source, mode="live-sentinel2")
        thread_class.call_args.kwargs["target"]()

    csv_save.assert_called_once_with(result, source, scan_id=scan_id)


def test_csv_history_adds_report_columns_without_losing_legacy_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scan_file = tmp_path / "scans.csv"
    finding_file = tmp_path / "findings.csv"
    monkeypatch.setattr(history, "SCAN_FILE", scan_file)
    monkeypatch.setattr(history, "FINDING_FILE", finding_file)
    legacy_scan_fields = history.SCAN_FIELDS[:-2]
    legacy_finding_fields = history.FINDING_FIELDS[:-4]

    with scan_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=legacy_scan_fields)
        writer.writeheader()
        writer.writerow({"scan_id": "legacy-scan", "changed_area_sqm": "20"})
    with finding_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=legacy_finding_fields)
        writer.writeheader()
        writer.writerow({
            "scan_id": "legacy-scan",
            "finding_id": "legacy-finding",
            "region_bbox_json": "[18.5,73.8,18.6,73.9]",
        })

    scan = history.read_scan("legacy-scan")
    findings = history.read_findings_for_scan("legacy-scan")

    assert scan is not None
    assert scan["scan_id"] == "legacy-scan"
    assert json.loads(scan["source_metadata"]) == {}
    assert findings[0]["original_finding_id"] == "legacy-finding"
    assert findings[0]["region_bbox"] == [18.5, 73.8, 18.6, 73.9]
