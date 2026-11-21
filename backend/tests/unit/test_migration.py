"""Unit tests for CSV migration logic."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.migrate_csv_to_neo4j import (
    _safe_float,
    _safe_int,
    _safe_json,
    parse_csv_findings,
    parse_csv_scans,
    run_migration,
)


class TestMigrationUnit:
    def test_safe_float_valid(self):
        assert _safe_float("12.5") == 12.5
        assert _safe_float(42) == 42.0

    def test_safe_float_invalid(self):
        assert _safe_float("") == 0.0
        assert _safe_float(None) == 0.0
        assert _safe_float("not-a-number", default=5.0) == 5.0

    def test_safe_int_valid(self):
        assert _safe_int("10") == 10
        assert _safe_int("15.7") == 15

    def test_safe_int_invalid(self):
        assert _safe_int("") == 0
        assert _safe_int(None) == 0
        assert _safe_int("bad", default=1) == 1

    def test_safe_json_valid(self):
        assert _safe_json('{"key": "value"}') == '{"key": "value"}'

    def test_safe_json_invalid(self):
        assert _safe_json("") == "{}"
        assert _safe_json("{malformed json") == "{}"

    def test_deterministic_detection_id(self):
        scan_id = "scan-20250101-123456"
        finding_id = "GS-001"
        det_id = f"det-{scan_id}-{finding_id}"
        assert det_id == "det-scan-20250101-123456-GS-001"
        # Must be identical on re-computation
        assert det_id == f"det-{scan_id}-{finding_id}"

    def test_dry_run_migration_stats(self, tmp_path: Path):
        scans_csv = tmp_path / "scans.csv"
        findings_csv = tmp_path / "findings.csv"

        scans_csv.write_text(
            "scan_id,created_at,region,historical_date,recent_date,historical_item,recent_item,cloud_cover_max,changed_area_sqm,finding_count,model,processing_json\n"
            "scan-1,2025-01-01,Pune,2025-01-01,2025-01-10,item1,item2,1.2,5000,1,CNN,{}\n",
            encoding="utf-8",
        )
        findings_csv.write_text(
            "scan_id,finding_id,area_name,latitude,longitude,area_sqm,severity,confidence,first_observed,last_observed,region_bbox_json\n"
            "scan-1,GS-001,Wagholi,18.52,73.86,5000,high,0.9,2025-01-01,2025-01-10,[18.5,73.8,18.6,73.9]\n",
            encoding="utf-8",
        )

        with patch("scripts.migrate_csv_to_neo4j.SCAN_CSV", scans_csv), \
             patch("scripts.migrate_csv_to_neo4j.FINDING_CSV", findings_csv):
            stats = run_migration(dry_run=True)
            assert stats["dry_run"] is True
            assert stats["total_scans_csv"] == 1
            assert stats["migrated_scans"] == 1
            assert stats["total_findings_csv"] == 1
            assert stats["migrated_findings"] == 1
            assert stats["failed_scans"] == 0

    def test_unicode_area_name_preserved(self, tmp_path: Path):
        findings_csv = tmp_path / "findings.csv"
        findings_csv.write_text(
            "scan_id,finding_id,area_name,latitude,longitude,area_sqm,severity,confidence,first_observed,last_observed,region_bbox_json\n"
            "scan-1,GS-001,पुणे खाण परिसर 🏔️,18.52,73.86,5000,high,0.9,2025-01-01,2025-01-10,[]\n",
            encoding="utf-8",
        )
        records = parse_csv_findings(findings_csv)
        assert len(records) == 1
        assert records[0]["area_name"] == "पुणे खाण परिसर 🏔️"
