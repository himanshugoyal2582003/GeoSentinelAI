# API routers

FastAPI routers expose health, scans, findings, investigations, graph queries,
monitoring sites, PDF reports, and evidence images. The static-region
`/api/live-detect` endpoints are registered in
[`../main.py`](../main.py).

Keep endpoint validation and HTTP response behavior in these route modules;
delegate domain operations to [`../services/`](../services/) and persistence
to [`../repositories/`](../repositories/). See the
[API reference](../../../docs/api-reference.md).
