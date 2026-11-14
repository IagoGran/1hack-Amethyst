# Tests

Place fast isolated tests in `tests/unit/` and tests that cross module or service boundaries in `tests/integration/`. Name files `test_<subject>.py` and test functions `test_<behavior>`.

Shared deterministic adapters and vendor clients live in `tests/support/`; they are excluded from the application package. Shared headless Qt setup is in `tests/integration/conftest.py`. Preview launchers and sample-data repositories have been removed. See `docs/code_structure.md` for the source module map and refactor boundaries.

Install development tools with `uv sync --group dev`, then run the suite with `uv run pytest`. Keep tests independent, deterministic, and free of real credentials or external service dependencies unless the test is explicitly marked and configured for them.
