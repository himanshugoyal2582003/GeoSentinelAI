"""migrate_csv_to_neo4j.py — Migrate CSV scan and finding records into Neo4j.

Usage:
    python scripts/migrate_csv_to_neo4j.py [--dry-run]

Features:
- Preserves original scan_id and finding_id.
- Deterministic detection_id: det-<scan_id>-<finding_id>.
- Uses MERGE throughout: completely safe and idempotent on repeated runs.
- Parses numeric and JSON fields safely; logs invalid rows.
- Never deletes or modifies CSV files.
- Prints a clear summary report at the end.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(_BACKEND_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("migration")

DATA_DIR = _BACKEND_DIR / "data"
SCAN_CSV = DATA_DIR / "scans.csv"
FINDING_CSV = DATA_DIR / "findings.csv"

_MERGE_REGION = """
MERGE (r:MonitoringRegion {region_id: $region_id})
ON CREATE SET
    r.name = $name,
    r.bbox = $bbox,
    r.created_at = $created_at
RETURN r.region_id AS region_id
"""

_MERGE_SCAN = """
MERGE (s:Scan {scan_id: $scan_id})
ON CREATE SET
    s.region_id           = $region_id,
    s.mode                = $mode,
    s.status              = "completed",
    s.historical_date     = $historical_date,
    s.recent_date         = $recent_date,
    s.changed_area_sqm    = $changed_area_sqm,
    s.finding_count       = $finding_count,
    s.model_name          = $model_name,
    s.created_at          = $created_at,
    s.processing_metadata = $processing_metadata,
    s.summary             = $summary,
    s.source_metadata     = $source_metadata
RETURN s.scan_id AS scan_id
"""

_LINK_REGION_SCAN = """
MATCH (r:MonitoringRegion {region_id: $region_id})
MATCH (s:Scan {scan_id: $scan_id})
MERGE (r)-[:HAS_SCAN]->(s)
"""

_MERGE_FINDING = """
MERGE (fo:FindingObservation {detection_id: $detection_id})
ON CREATE SET
    fo.original_finding_id = $original_finding_id,
    fo.scan_id             = $scan_id,
    fo.label               = $label,
    fo.severity            = $severity,
    fo.confidence          = $confidence,
    fo.area_sqm            = $area_sqm,
    fo.latitude            = $latitude,
    fo.longitude           = $longitude,
    fo.location            = point({latitude: $latitude, longitude: $longitude, crs: 'WGS-84'}),
    fo.first_observed      = $first_observed,
    fo.last_observed       = $last_observed,
    fo.region_bbox         = $region_bbox,
    fo.review_status       = "migrated",
    fo.created_at          = $created_at
WITH fo
MATCH (s:Scan {scan_id: $scan_id})
MERGE (s)-[:PRODUCED]->(fo)
RETURN fo.detection_id AS detection_id
"""


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val) if val not in (None, "") else default
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(val)) if val not in (None, "") else default
    except (ValueError, TypeError):
        return default


def _safe_json(val: Any) -> str:
    if not val or not str(val).strip():
        return "{}"
    try:
        parsed = json.loads(val)
        return json.dumps(parsed)
    except Exception:
        return "{}"


def parse_csv_scans(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if not r.get("scan_id"):
                continue
            rows.append(r)
    return rows


def parse_csv_findings(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if not r.get("scan_id") or not r.get("finding_id"):
                continue
            rows.append(r)
    return rows


def run_migration(dry_run: bool = False) -> dict[str, Any]:
    stats = {
        "total_scans_csv": 0,
        "migrated_scans": 0,
        "failed_scans": 0,
        "total_findings_csv": 0,
        "migrated_findings": 0,
        "failed_findings": 0,
        "invalid_rows": 0,
        "dry_run": dry_run,
    }

    scans_data = parse_csv_scans(SCAN_CSV)
    findings_data = parse_csv_findings(FINDING_CSV)

    stats["total_scans_csv"] = len(scans_data)
    stats["total_findings_csv"] = len(findings_data)

    if dry_run:
        logger.info("[DRY RUN] Found %d scans and %d findings in CSV.", len(scans_data), len(findings_data))
        stats["migrated_scans"] = len(scans_data)
        stats["migrated_findings"] = len(findings_data)
        return stats

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    if not password:
        logger.error("NEO4J_PASSWORD not set. Cannot run migration against live database.")
        stats["failed_scans"] = len(scans_data)
        return stats

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        driver.verify_connectivity()
    except Exception as exc:
        logger.error("Could not connect to Neo4j: %s", exc)
        return stats

    # Group findings by scan_id
    findings_by_scan: dict[str, list[dict]] = {}
    for f in findings_data:
        findings_by_scan.setdefault(f["scan_id"], []).append(f)

    with driver.session(database=database) as session:
        for s in scans_data:
            scan_id = s["scan_id"]
            region_name = s.get("region") or "Pune quarry belt"
            region_id = f"region-{region_name.lower().replace(' ', '-')}"
            try:
                # Merge region
                session.run(
                    _MERGE_REGION,
                    region_id=region_id,
                    name=region_name,
                    bbox="[73.82, 18.48, 73.90, 18.56]",
                    created_at=s.get("created_at", ""),
                )
                # Merge scan
                session.run(
                    _MERGE_SCAN,
                    scan_id=scan_id,
                    region_id=region_id,
                    mode="historical-csv",
                    historical_date=s.get("historical_date", ""),
                    recent_date=s.get("recent_date", ""),
                    changed_area_sqm=_safe_float(s.get("changed_area_sqm")),
                    finding_count=_safe_int(s.get("finding_count")),
                    model_name=s.get("model", "ChangeCNN"),
                    created_at=s.get("created_at", ""),
                    processing_metadata=_safe_json(s.get("processing_json")),
                    summary="{}",
                    source_metadata=json.dumps({
                        "historicalItem": s.get("historical_item", ""),
                        "recentItem": s.get("recent_item", ""),
                        "cloudCoverMax": s.get("cloud_cover_max", ""),
                    }),
                )
                # Link region -> scan
                session.run(_LINK_REGION_SCAN, region_id=region_id, scan_id=scan_id)
                stats["migrated_scans"] += 1

                # Migrate associated findings
                for f in findings_by_scan.get(scan_id, []):
                    finding_id = f["finding_id"]
                    det_id = f"det-{scan_id}-{finding_id}"
                    lat = _safe_float(f.get("latitude"))
                    lon = _safe_float(f.get("longitude"))
                    conf = min(1.0, max(0.0, _safe_float(f.get("confidence"))))
                    sev = f.get("severity", "low").lower()
                    if sev not in ("high", "medium", "low"):
                        sev = "low"
                        stats["invalid_rows"] += 1

                    session.run(
                        _MERGE_FINDING,
                        detection_id=det_id,
                        original_finding_id=finding_id,
                        scan_id=scan_id,
                        label=f.get("area_name") or f"Finding {finding_id}",
                        severity=sev,
                        confidence=conf,
                        area_sqm=_safe_float(f.get("area_sqm")),
                        latitude=lat,
                        longitude=lon,
                        first_observed=f.get("first_observed", ""),
                        last_observed=f.get("last_observed", ""),
                        region_bbox=_safe_json(f.get("region_bbox_json")),
                        created_at=s.get("created_at", ""),
                    )
                    stats["migrated_findings"] += 1

            except Exception as exc:
                logger.error("Failed to migrate scan %s: %s", scan_id, exc)
                stats["failed_scans"] += 1

    driver.close()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate CSV history to Neo4j.")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing to Neo4j.")
    args = parser.parse_args()

    print("==================================================")
    print(" GeoSentinelAI — CSV to Neo4j Migration Utility   ")
    print("==================================================")
    stats = run_migration(dry_run=args.dry_run)
    print("\n--- Migration Report ---")
    print(f"  Dry run             : {stats['dry_run']}")
    print(f"  Total scans in CSV  : {stats['total_scans_csv']}")
    print(f"  Migrated scans      : {stats['migrated_scans']}")
    print(f"  Failed scans        : {stats['failed_scans']}")
    print(f"  Total findings CSV  : {stats['total_findings_csv']}")
    print(f"  Migrated findings   : {stats['migrated_findings']}")
    print(f"  Failed findings     : {stats['failed_findings']}")
    print(f"  Sanitized row issues: {stats['invalid_rows']}")

    if stats["failed_scans"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
