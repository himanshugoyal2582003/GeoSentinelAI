from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from PIL import Image

from app.api import pdf_reports


@pytest.fixture
def report_data(tmp_path: Path) -> dict[str, Any]:
    capture_id = "a" * 32
    for name, color in (("historical", (96, 128, 80)), ("recent", (120, 144, 88))):
        Image.new("RGB", (256, 256), color).save(
            tmp_path / f"{name}-{capture_id}.png",
            format="PNG",
        )

    scan = {
        "scan_id": "scan-123",
        "status": "completed",
        "historical_date": "2025-01-01",
        "recent_date": "2025-10-01",
        "source_metadata": json.dumps({
            "bbox": [73.82, 18.48, 73.90, 18.56],
            "imageCaptureId": capture_id,
            "resolutionMeters": 10,
            "assetType": "Native Sentinel-2 L2A COG",
        }),
        "processing_metadata": json.dumps({"cloudMaskFraction": 0.05}),
        "summary": json.dumps({"changedAreaSqm": 15000}),
    }
    findings = [{
        "original_finding_id": "GS-LIVE-001",
        "label": "Detected change",
        "area_sqm": 15000,
        "confidence": 0.87,
        "latitude": 18.52,
        "longitude": 73.86,
        "region_bbox": [18.51, 73.85, 18.53, 73.87],
    }]
    return {"scan": scan, "findings": findings, "media_dir": tmp_path}


@pytest.mark.parametrize("template", ["quarry-compliance", "landowner-evidence"])
def test_build_pdf_report_creates_one_page_with_scan_images(report_data: dict, template: str) -> None:
    pdf_bytes = pdf_reports.build_pdf_report(
        report_data["scan"],
        report_data["findings"],
        template=template,
        brand_name="Test Brand",
        finding_id="GS-LIVE-001",
        media_dir=report_data["media_dir"],
    )

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf_bytes)) == 1


def test_build_pdf_report_rejects_finding_outside_scan(report_data: dict) -> None:
    with pytest.raises(HTTPException) as exc_info:
        pdf_reports.build_pdf_report(
            report_data["scan"],
            report_data["findings"],
            template="quarry-compliance",
            brand_name="Test Brand",
            finding_id="not-in-this-scan",
            media_dir=report_data["media_dir"],
        )

    assert exc_info.value.status_code == 404


@pytest.mark.parametrize(
    ("source", "processing", "has_images", "expected_status"),
    [
        ({}, {"cloudMaskFraction": 0.25}, True, "CLOUDY / INCONCLUSIVE"),
        ({}, {"cloudMaskFraction": 0.05}, False, "INCONCLUSIVE"),
    ],
)
def test_cloud_and_missing_imagery_are_not_reported_as_reviewable(
    report_data: dict,
    source: dict,
    processing: dict,
    has_images: bool,
    expected_status: str,
) -> None:
    status, _, _ = pdf_reports._cloud_status(
        report_data["scan"],
        source,
        processing,
        has_images,
        report_data["findings"][0],
    )

    assert status == expected_status


def test_report_endpoint_returns_pdf_attachment(report_data: dict) -> None:
    session = MagicMock()
    session.__enter__.return_value = session
    with (
        patch.object(pdf_reports, "get_session", return_value=session),
        patch.object(pdf_reports.scan_repository, "get_scan", return_value=report_data["scan"]),
        patch.object(
            pdf_reports.finding_repository,
            "list_findings_for_scan",
            return_value=report_data["findings"],
        ),
    ):
        response = pdf_reports.download_scan_report(
            "scan-123",
            template="landowner-evidence",
            brand_name="Test Brand",
            finding_id="GS-LIVE-001",
        )

    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"].endswith("landowner-evidence.pdf\"")
    assert response.body.startswith(b"%PDF-")


def test_report_endpoint_falls_back_to_csv_when_neo4j_is_unavailable(report_data: dict) -> None:
    with (
        patch.object(pdf_reports, "get_session", side_effect=RuntimeError("Neo4j unavailable")),
        patch.object(pdf_reports, "read_csv_scan", return_value=report_data["scan"]),
        patch.object(
            pdf_reports,
            "read_csv_findings_for_scan",
            return_value=report_data["findings"],
        ),
    ):
        response = pdf_reports.download_scan_report(
            "scan-123",
            template="quarry-compliance",
            brand_name="Test Brand",
            finding_id="GS-LIVE-001",
        )

    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF-")


def test_scan_image_endpoint_streams_durable_storage_asset() -> None:
    scan = {
        "source_metadata": json.dumps({"historicalImageAssetUri": "r2://bucket/key"}),
    }

    with (
        patch.object(pdf_reports, "_load_scan_record", return_value=(scan, False)),
        patch.object(pdf_reports, "read_evidence_bytes", return_value=b"png-data") as read_bytes,
    ):
        response = pdf_reports.download_scan_image("scan-123", "historical")

    assert response.media_type == "image/png"
    assert response.body == b"png-data"
    read_bytes.assert_called_once_with("r2://bucket/key")


def test_report_endpoint_returns_404_for_missing_scan() -> None:
    session = MagicMock()
    session.__enter__.return_value = session
    with (
        patch.object(pdf_reports, "get_session", return_value=session),
        patch.object(pdf_reports.scan_repository, "get_scan", return_value=None),
        patch.object(pdf_reports, "read_csv_scan", return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            pdf_reports.download_scan_report("missing")

    assert exc_info.value.status_code == 404
