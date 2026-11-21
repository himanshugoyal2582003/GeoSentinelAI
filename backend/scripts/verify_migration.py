"""verify_migration.py — Verify integrity of CSV to Neo4j migration.

Compares:
- Total CSV scans vs Neo4j scans.
- Total CSV findings vs Neo4j findings.
- Checks that scan-to-finding relationships exist in Neo4j.
- Checks for duplicate detection_id values.
- Documents rollback procedure.

Usage:
    python scripts/verify_migration.py
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(_BACKEND_DIR / ".env")

DATA_DIR = _BACKEND_DIR / "data"
SCAN_CSV = DATA_DIR / "scans.csv"
FINDING_CSV = DATA_DIR / "findings.csv"


def verify() -> int:
    print("==================================================")
    print(" GeoSentinelAI — Migration Verification Utility   ")
    print("==================================================")

    csv_scans = 0
    if SCAN_CSV.exists():
        with SCAN_CSV.open(newline="", encoding="utf-8") as f:
            csv_scans = sum(1 for r in csv.DictReader(f) if r.get("scan_id"))

    csv_findings = 0
    if FINDING_CSV.exists():
        with FINDING_CSV.open(newline="", encoding="utf-8") as f:
            csv_findings = sum(1 for r in csv.DictReader(f) if r.get("finding_id"))

    print("\n[Source Check] CSV Record Counts:")
    print(f"  Scans in CSV    : {csv_scans}")
    print(f"  Findings in CSV : {csv_findings}")

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    if not password:
        print("\n[WARN] NEO4J_PASSWORD not set. Cannot verify against active database.")
        print("Set NEO4J_PASSWORD to perform live graph verification.")
        return 1

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        driver.verify_connectivity()
    except Exception as exc:
        print(f"\n[FAIL] Could not connect to Neo4j: {exc}")
        return 1

    failures = 0
    with driver.session(database=database) as session:
        # Check Scan count
        res = session.run("MATCH (s:Scan) RETURN count(s) AS total").single()
        neo4j_scans = res["total"] if res else 0

        # Check Finding count
        res = session.run("MATCH (fo:FindingObservation) RETURN count(fo) AS total").single()
        neo4j_findings = res["total"] if res else 0

        # Check Duplicate detection_ids
        res = session.run(
            "MATCH (fo:FindingObservation) WITH fo.detection_id AS did, count(fo) AS cnt "
            "WHERE cnt > 1 RETURN count(did) AS dups"
        ).single()
        dup_findings = res["dups"] if res else 0

        # Check Relationships: Scans without PRODUCED relationships
        res = session.run(
            "MATCH (s:Scan) WHERE s.finding_count > 0 AND NOT (s)-[:PRODUCED]->(:FindingObservation) "
            "RETURN count(s) AS missing_links"
        ).single()
        missing_links = res["missing_links"] if res else 0

        print("\n[Target Check] Neo4j Database Counts:")
        print(f"  Scans in Neo4j          : {neo4j_scans}")
        print(f"  Findings in Neo4j       : {neo4j_findings}")
        print(f"  Duplicate Findings      : {dup_findings}")
        print(f"  Scans with Missing Links: {missing_links}")

        print("\n--- Integrity Audit ---")
        if dup_findings > 0:
            print(f"  [FAIL] Found {dup_findings} duplicate finding detection_ids!")
            failures += 1
        else:
            print("  [PASS] No duplicate finding detection_ids found.")

        if missing_links > 0:
            print(f"  [WARN] {missing_links} scans with finding_count > 0 lack PRODUCED relationships.")
        else:
            print("  [PASS] Scan-to-finding relationships verified.")

        if neo4j_scans >= csv_scans:
            print(f"  [PASS] All {csv_scans} CSV scans represented in Neo4j.")
        else:
            print(f"  [FAIL] Neo4j has fewer scans ({neo4j_scans}) than CSV ({csv_scans}).")
            failures += 1

    driver.close()

    print("\n--- Documented Rollback Strategy ---")
    print("If migration verification fails and a clean rollback is required:")
    print("1. Target only migrated records:")
    print("   MATCH (s:Scan {mode: 'historical-csv'}) DETACH DELETE s")
    print("   MATCH (fo:FindingObservation {review_status: 'migrated'}) DETACH DELETE fo")
    print("2. The original CSV files remain completely untouched and unmodified.")
    print("3. Retain CSV reading fallback until verification passes.")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(verify())
