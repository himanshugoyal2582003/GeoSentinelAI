# Repositories

Repository modules encapsulate Neo4j queries for scans, findings, regions,
scenes, evidence, cases, and alerts. Application services should use these
functions rather than duplicate Cypher queries.

Add focused unit tests under [`backend/tests/unit/`](../../tests/unit/)
when repository behavior changes; use integration tests for real Neo4j
contracts.
