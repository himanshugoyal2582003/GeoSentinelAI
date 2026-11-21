# Integration tests

Integration tests verify behavior against real infrastructure such as Neo4j.
Use a dedicated disposable test database and explicit test credentials; never
point these tests at production data.

Run from `backend/` with
`.\.venv\Scripts\python.exe -m pytest tests/integration` after configuring the
integration environment.
