# Backend scripts

Scripts in this directory initialize Neo4j schema, migrate CSV history, and
verify migration results. Run them from `backend/` so the `app` package and
environment configuration resolve correctly.

Review the script's `--help` output before running a migration against a
non-test database. See [`docs/data-model.md`](../../docs/data-model.md).
