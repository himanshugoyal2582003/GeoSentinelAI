"""Unit tests for Pydantic domain models in GeoSentinelAI."""
from __future__ import annotations

import math
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.scan import Scan, ScanCreate, ScanStatus, ScanSummary
from app.models.finding import FindingCreate, FindingObservation, Severity
from app.models.scene import SceneCreate, SatelliteScene
from app.models.evidence import EvidenceAssetCreate, EvidenceAsset
from app.models.investigation import InvestigationCreate, InvestigationCase, CaseStatus


class TestScanModels:
    def test_valid_scan_create(self):
        data = {
            "scan_id": "scan-123",
            "mode": "live-sentinel2",
            "region_id": "region-pune",
            "historical_date": "2025-01-01",
            "recent_date": "2025-10-01",
            "changed_area_sqm": 12500.0,
            "finding_count": 3,
            "model_name": "ChangeCNN",
            "processing_metadata": {"threshold": 30.5},
            "summary": {"changedAreaSqm": 12500},
            "source_metadata": {"provider": "Copernicus"},
            "status": "completed",
            "idempotency_key": "key-xyz",
        }
        sc = ScanCreate(**data)
        assert sc.scan_id == "scan-123"
        assert sc.changed_area_sqm == 12500.0
        assert sc.idempotency_key == "key-xyz"

    def test_scan_empty_id_raises(self):
        with pytest.raises(ValidationError):
            ScanCreate(
                scan_id="",
                mode="live",
                region_id="r1",
                historical_date="2025-01-01",
                recent_date="2025-02-01",
                changed_area_sqm=10.0,
                finding_count=1,
                model_name="CNN",
            )

    def test_scan_negative_area_raises(self):
        with pytest.raises(ValidationError):
            ScanCreate(
                scan_id="s1",
                mode="live",
                region_id="r1",
                historical_date="2025-01-01",
                recent_date="2025-02-01",
                changed_area_sqm=-100.0,
                finding_count=0,
                model_name="CNN",
            )

    def test_scan_unicode_metadata(self):
        data = {
            "scan_id": "scan-unicode-123",
            "mode": "live",
            "region_id": "region-पुणे",
            "historical_date": "2025-01-01",
            "recent_date": "2025-10-01",
            "changed_area_sqm": 0.0,
            "finding_count": 0,
            "model_name": "ChangeCNN",
            "processing_metadata": {"note": "पुणे खाण परिसर 🔍"},
        }
        sc = ScanCreate(**data)
        assert sc.region_id == "region-पुणे"
        assert sc.processing_metadata["note"] == "पुणे खाण परिसर 🔍"


class TestFindingModels:
    def test_valid_finding(self):
        f = FindingCreate(
            detection_id="det-001",
            original_finding_id="GS-001",
            scan_id="scan-001",
            label="Quarry extraction",
            severity=Severity.high,
            confidence=0.88,
            area_sqm=5000.0,
            latitude=18.52,
            longitude=73.86,
            first_observed="2025-01-01",
            last_observed="2025-10-01",
            detection_error_sqm=150.0,
            region_bbox=[18.50, 73.84, 18.54, 73.88],
        )
        assert f.detection_id == "det-001"
        assert f.severity == Severity.high
        assert f.confidence == 0.88

    def test_invalid_confidence_above_one(self):
        with pytest.raises(ValidationError):
            FindingCreate(
                detection_id="det-001",
                original_finding_id="GS-001",
                scan_id="scan-001",
                label="Change",
                severity=Severity.medium,
                confidence=1.5,
                area_sqm=100.0,
                latitude=18.0,
                longitude=73.0,
                first_observed="2025-01-01",
                last_observed="2025-10-01",
                detection_error_sqm=10.0,
                region_bbox=[18.0, 73.0, 18.1, 73.1],
            )

    def test_invalid_confidence_nan(self):
        with pytest.raises(ValidationError):
            FindingCreate(
                detection_id="det-001",
                original_finding_id="GS-001",
                scan_id="scan-001",
                label="Change",
                severity=Severity.low,
                confidence=float("nan"),
                area_sqm=100.0,
                latitude=18.0,
                longitude=73.0,
                first_observed="2025-01-01",
                last_observed="2025-10-01",
                detection_error_sqm=10.0,
                region_bbox=[18.0, 73.0, 18.1, 73.1],
            )

    def test_invalid_coordinates_out_of_bounds(self):
        with pytest.raises(ValidationError):
            FindingCreate(
                detection_id="det-001",
                original_finding_id="GS-001",
                scan_id="scan-001",
                label="Change",
                severity=Severity.low,
                confidence=0.5,
                area_sqm=100.0,
                latitude=95.0,  # invalid: > 90
                longitude=73.0,
                first_observed="2025-01-01",
                last_observed="2025-10-01",
                detection_error_sqm=10.0,
                region_bbox=[18.0, 73.0, 18.1, 73.1],
            )

    def test_invalid_bbox_length(self):
        with pytest.raises(ValidationError):
            FindingCreate(
                detection_id="det-001",
                original_finding_id="GS-001",
                scan_id="scan-001",
                label="Change",
                severity=Severity.low,
                confidence=0.5,
                area_sqm=100.0,
                latitude=18.0,
                longitude=73.0,
                first_observed="2025-01-01",
                last_observed="2025-10-01",
                detection_error_sqm=10.0,
                region_bbox=[18.0, 73.0],  # only 2 elements
            )


class TestSceneAndEvidenceModels:
    def test_valid_scene(self):
        scene = SceneCreate(
            scene_id="S2A_123",
            provider="Planetary Computer",
            acquired_at=datetime.now(timezone.utc),
            cloud_cover=12.4,
            asset_metadata={"eo:cloud_cover": 12.4},
        )
        assert scene.scene_id == "S2A_123"
        assert scene.cloud_cover == 12.4

    def test_optional_cloud_cover_none(self):
        scene = SceneCreate(
            scene_id="S2A_124",
            provider="Planetary Computer",
            acquired_at=datetime.now(timezone.utc),
            cloud_cover=None,
        )
        assert scene.cloud_cover is None

    def test_valid_evidence_asset(self):
        asset = EvidenceAssetCreate(
            asset_id="asset-1",
            uri="/media/evidence/diff.png",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            media_type="image/png",
            file_size=2048,
            asset_type="diff_image",
        )
        assert asset.file_size == 2048
        assert len(asset.sha256) == 64


class TestInvestigationModels:
    def test_investigation_case(self):
        case = InvestigationCreate(
            title="Wagholi Quarry Survey 2025",
            description="Inspection of recent expanding pit boundaries",
            status=CaseStatus.open,
        )
        assert case.title == "Wagholi Quarry Survey 2025"
        assert case.status == CaseStatus.open
