"""
init_neo4j_schema.py — Standalone script to initialise Neo4j constraints and indexes.

Usage:
    python scripts/init_neo4j_schema.py

Environment variables (or backend/.env):
    NEO4J_URI       — bolt:// or bolt+s:// or neo4j+s:// URI
    NEO4J_USERNAME  — database username (default: neo4j)
    NEO4J_PASSWORD  — database password
    NEO4J_DATABASE  — target database (default: neo4j)

Exit codes:
    0 — success
    1 — failure
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root or from scripts/ directory
_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(_BACKEND_DIR / ".env")

import os


def main() -> int:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    print("GeoSentinelAI — Neo4j Schema Initialiser")
    print(f"  URI      : {uri}")
    print(f"  Username : {username}")
    print(f"  Database : {database}")
    print()

    if not password:
        print("ERROR: NEO4J_PASSWORD is not set.", file=sys.stderr)
        return 1

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print(
            "ERROR: neo4j Python driver not installed. Run: pip install neo4j",
            file=sys.stderr,
        )
        return 1

    try:
        from app.db.schema import initialize_schema, verify_schema
    except ImportError as exc:
        print(f"ERROR: Could not import schema module: {exc}", file=sys.stderr)
        return 1

    driver = None
    try:
        driver = GraphDatabase.driver(uri, auth=(username, password))
        driver.verify_connectivity()

        print("Connected. Initialising schema …")
        initialize_schema(driver, database)

        result = verify_schema(driver, database)
        constraints = result.get("constraints", [])
        indexes = result.get("indexes", [])

        print("\nSchema ready.")
        print(f"  Constraints : {len(constraints)}")
        for c in constraints:
            name = c.get("name", str(c))
            print(f"    - {name}")
        print(f"  Indexes     : {len(indexes)}")
        for idx in indexes:
            name = idx.get("name", str(idx))
            print(f"    - {name}")

        print("\nDone — exit 0.")
        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if driver is not None:
            driver.close()


if __name__ == "__main__":
    sys.exit(main())
