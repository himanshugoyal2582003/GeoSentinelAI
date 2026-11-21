# API tests

These tests exercise FastAPI endpoints, validation, and response contracts
using the shared fixtures in [`../conftest.py`](../conftest.py). They should
not require external provider credentials or a production database.

Run from `backend/` with `python -m pytest tests/api`.
