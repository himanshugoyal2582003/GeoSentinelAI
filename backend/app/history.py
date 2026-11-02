from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SCAN_FILE = DATA_DIR / "scans.csv"
FINDING_FILE = DATA_DIR / "findings.csv"
SCAN_FIELDS = [
    "scan_id", "created_at", "region", "historical_date", "recent_date",
    "historical_item", "recent_item", "cloud_cover_max", "changed_area_sqm",
    "finding_count", "model", "processing_json",
]
FINDING_FIELDS = [
    "scan_id", "finding_id", "area_name", "latitude", "longitude", "area_sqm",
    "severity", "confidence", "first_observed", "last_observed", "region_bbox_json",
]


def _ensure(path: Path, fields: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.DictWriter(handle, fieldnames=fields).writeheader()


def save_scan(result: dict[str, Any], source: dict[str, Any]) -> str:
    scan_id = f"scan-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
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
            })
    return scan_id


def read_scans(limit: int = 50) -> list[dict[str, str]]:
    _ensure(SCAN_FILE, SCAN_FIELDS)
    with SCAN_FILE.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))[-limit:][::-1]

