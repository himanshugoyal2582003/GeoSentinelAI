# Backend application

The `app` package owns the FastAPI entry point and supporting analysis and
domain modules. [`main.py`](./main.py) wires routers, acquisition,
multispectral processing, and the static-region live-scan cache.

- [`api/`](./api/) defines HTTP routers.
- [`db/`](./db/) configures Neo4j and schema.
- [`models/`](./models/) defines persisted domain entities.
- [`repositories/`](./repositories/) reads and writes graph records.
- [`services/`](./services/) implements application workflows.
- [`worker/`](./worker/) runs scheduled site scans and alerts.

See the [API reference](../../docs/api-reference.md) and
[system architecture](../../docs/system-architecture.md) for contracts and
component boundaries.
