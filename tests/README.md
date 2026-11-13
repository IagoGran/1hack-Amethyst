# Tests

Place fast isolated tests in `tests/unit/` and tests that cross module or service boundaries in `tests/integration/`. Name files `test_<subject>.py` and test functions `test_<behavior>`.

Install development tools with `uv sync --group dev`, then run the suite with `uv run pytest`. Keep tests independent, deterministic, and free of real credentials or external service dependencies unless the test is explicitly marked and configured for them.
