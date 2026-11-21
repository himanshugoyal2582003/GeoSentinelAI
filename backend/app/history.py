from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SCAN_FILE = DATA_DIR / "scans.csv"
FINDING_FILE = DATA_DIR / "findings.csv"
SCAN_FIELDS = [
    "scan_id", "created_at", "region", "historical_date", "recent_date",
    "historical_item", "recent_item", "cloud_cover_max", "changed_area_sqm",
    "finding_count", "model", "processing_json", "source_metadata_json",
    "summary_json",
]
FINDING_FIELDS = [
    "scan_id", "finding_id", "area_name", "latitude", "longitude", "area_sqm",
    "severity", "confidence", "first_observed", "last_observed", "region_bbox_json",
    "label", "change_type", "model_score", "detection_error_sqm",
]
_HISTORY_LOCK = RLock()


def _ensure(path: Path, fields: list[str]) -> None:
    with _HISTORY_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open("w", newline="", encoding="utf-8") as handle:
                csv.DictWriter(handle, fieldnames=fields).writeheader()
            return

        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            existing_fields = reader.fieldnames or []
            if all(field in existing_fields for field in fields):
                return
            rows = list(reader)

        temporary_path = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
        with temporary_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        temporary_path.replace(path)


def save_scan(
    result: dict[str, Any],
    source: dict[str, Any],
    scan_id: str | None = None,
) -> str:
    if scan_id is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        scan_id = f"scan-{timestamp}-{uuid4().hex[:6]}"
    _ensure(SCAN_FILE, SCAN_FIELDS)
    _ensure(FINDING_FILE, FINDING_FIELDS)
    with SCAN_FILE.open("a", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=SCAN_FIELDS).writerow({
            "scan_id": scan_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "region": result["region"],
            "historical_date": result["historicalDate"],
            "recent_date": result["recentDate"],
            "historical_item": source.get("historicalItem", ""),
            "recent_item": source.get("recentItem", ""),
            "cloud_cover_max": source.get("recentCloudCover", ""),
            "changed_area_sqm": result["summary"]["changedAreaSqm"],
            "finding_count": len(result["findings"]),
            "model": result["processing"]["model"],
            "processing_json": json.dumps(result["processing"]),
            "source_metadata_json": json.dumps(source),
            "summary_json": json.dumps(result["summary"]),
        })
    with FINDING_FILE.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FINDING_FIELDS)
        for finding in result["findings"]:
            writer.writerow({
                "scan_id": scan_id,
                "finding_id": finding["id"],
                "area_name": finding.get("areaName", ""),
                "latitude": finding["coordinates"][0],
                "longitude": finding["coordinates"][1],
                "area_sqm": finding["areaSqm"],
                "severity": finding["severity"],
                "confidence": finding["confidence"],
                "first_observed": finding["firstObserved"],
                "last_observed": finding["lastObserved"],
                "region_bbox_json": json.dumps(finding.get("regionBbox", [])),
                "label": finding.get("label", ""),
                "change_type": finding.get("changeType", ""),
                "model_score": finding.get("modelScore", ""),
                "detection_error_sqm": finding.get("detectionErrorSqm", ""),
            })
    return scan_id


def read_scan(scan_id: str) -> dict[str, str] | None:
    _ensure(SCAN_FILE, SCAN_FIELDS)
    with SCAN_FILE.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("scan_id") == scan_id:
                row.update({
                    "status": "completed",
                    "region_name": row.get("region", ""),
                    "processing_metadata": row.get("processing_json") or "{}",
                    "source_metadata": row.get("source_metadata_json") or "{}",
                    "summary": row.get("summary_json") or json.dumps({
                        "changedAreaSqm": row.get("changed_area_sqm", 0),
                    }),
                })
                return row
    return None


def read_findings_for_scan(scan_id: str) -> list[dict[str, Any]]:
    _ensure(FINDING_FILE, FINDING_FIELDS)
    findings = []
    with FINDING_FILE.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("scan_id") != scan_id:
                continue
            try:
                region_bbox = json.loads(row.get("region_bbox_json") or "[]")
            except json.JSONDecodeError as exc:
                raise ValueError(f"Stored finding {row.get('finding_id')} has invalid region bounds.") from exc
            findings.append({
                **row,
                "original_finding_id": row.get("finding_id", ""),
                "region_bbox": region_bbox,
            })
    return findings


def read_scans(limit: int = 50) -> list[dict[str, str]]:
    _ensure(SCAN_FILE, SCAN_FIELDS)
    with SCAN_FILE.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))[-limit:][::-1]

