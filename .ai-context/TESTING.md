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

## Approved MVP Acceptance Gate

Requirements section 5.8 defines the release gate; implementation and results remain `Pending`.

- All critical-path tests must pass: approval denial/revocation, lifetime and batch scope, changed-diff invalidation, read-only SQL, sandbox boundaries and default network denial, cancellation, timeouts/retries, budget enforcement, secret redaction, and task-state consistency.
- Achieve at least 80% aggregate branch coverage across `domain/`, `application/`, and `security/`. Coverage tooling and enforcement configuration: `Pending`.
- Provide adapter contract tests for OpenAI API, Gemini API, DeepSeek API, local Ollama, SQLite 3, PostgreSQL 16+, locally hosted Qdrant/Milvus/ChromaDB, and Brave Search API.
- Run desktop smoke tests on Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2. Include chat, settings, approvals, conversation viewing/resumption/deletion, and sandboxed command/test execution.
- Verify retention and credential handling: conversations remain until deleted, ordinary redacted logs expire after seven days, explicitly saved logs persist until deleted, temporary raw data is cleaned up, and unavailable credential stores trigger memory-only fallback.
- Deterministic automated checks must run without live credentials. Live-service and performance checks require explicit configuration and separate environment reporting.

## Performance Acceptance

Measure p95 over at least 30 runs per tested reference configuration, recording hardware, OS, model/provider, and network conditions. A typical task uses at most three tool calls and 1,000 generated tokens. Exclude user-approval waits and report local-model cold starts separately.

- First visible model token: at most 10 seconds from request dispatch for streaming-capable models.
- Typical task: at most 120 seconds from submission to completion.
- UI status feedback: at most 200 milliseconds after a user action.

Verify configurable operational defaults and limit enforcement against requirements sections 5.5 and 5.6. Benchmark fixtures and reference configurations: `Pending`; these targets have not been measured yet.
