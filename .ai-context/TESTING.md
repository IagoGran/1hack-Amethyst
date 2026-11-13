# Testing

## Framework and Layout

- Use `pytest`.
- Put unit tests under `tests/unit/` and integration tests under `tests/integration/`.
- Name test modules `test_<subject>.py` and test functions `test_<behavior>`.
- Keep tests independent and deterministic. Do not require live services or real credentials unless explicitly configured for an integration test.

## Commands

- Install development dependencies: `uv sync --group dev`.
- Run tests: `uv run pytest`.
- Run an individual test module: `uv run pytest tests/path/to/test_module.py`.

## Type Checking

Use gradual typing with `mypy`. Annotate new and modified interfaces and functions where useful; unannotated legacy code remains allowed. Run `uv run mypy`.

## Test Policy

Add or update tests for behavior changes and important permission, tool execution, and task-state paths (NFR-12). Do not run tests unless the user requests testing or the agreed task workflow explicitly requires it. Report any checks that were not run.
