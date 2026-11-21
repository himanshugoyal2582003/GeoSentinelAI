# Scheduled worker

[`cron_scan.py`](./cron_scan.py) checks active monitoring sites and scans
sites that are due according to the five-day minimum cadence. It also queues
and dispatches threshold-qualified email alerts.

The Render cron service is configured at the repository root in
[`render.yaml`](../../../render.yaml). Worker behavior is covered by
[`test_phase5.py`](../../tests/unit/test_phase5.py).
