# Backend tests

Run the suite from `backend/` with
`.\.venv\Scripts\python.exe -m pytest`. Unit and API tests use mocks for
external services; integration tests require an explicitly configured test
Neo4j database.

- [`unit/`](./unit/) tests analysis, persistence, caching, and services.
- [`api/`](./api/) tests HTTP contracts and access controls.
- [`integration/`](./integration/) tests Neo4j behavior.

Use safe test environment variables and disable dotenv loading when a local
environment file is present.
