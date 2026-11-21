# Application services

Services implement reusable workflows for detection, persistence,
investigations, graph operations, evidence storage, alerts, and scheduled
notification delivery. HTTP routers and workers should delegate domain logic
here.

External providers and databases should be mocked in unit tests. See
[`backend/tests/unit/`](../../tests/unit/).
