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

Use gradual typing with `mypy`. Annotate new and modified interfaces and functions where useful; unannotated legacy code remains allowed. Run `uv run mypy src tests` to check both implementation and the tests that assign doubles to port types.

## Test Policy

Add or update tests for behavior changes and important permission, tool execution, and task-state paths (NFR-12). Do not run tests unless the user requests testing or the agreed task workflow explicitly requires it. Report any checks that were not run.

## S0 Baseline Checks

`tests/unit/test_contract_baseline.py` checks fake model/tool results, task event ordering/replay, cancellation, repository snapshot isolation, memory credentials, deny-all approvals, and disabled sandbox behavior. `tests/integration/test_launch.py` checks the provisional module launcher. Run the suite without live services or credentials. S0 requires Ruff lint/format checks, mypy, pytest, a package build, and a fresh-wheel import/CLI smoke check before merging into `dev`. These checks do not establish desktop acceptance, durable retention, or the MVP coverage gate.

`tests/unit/test_integrations.py` adds credential-free contract coverage for SQLite repository restart behavior, SQLite read-only enforcement and output bounds, provider stream translation, Brave source attribution, vector adapter limits/source IDs, connection validation, and connection CRUD. PostgreSQL uses an opt-in driver; live adapter checks remain separately configured. The full offline suite passed with 23 tests on 2026-11-13; this does not establish live-service acceptance.

## Approved MVP Acceptance Gate

Requirements section 5.8 defines the release gate; implementation and results remain `Pending`.

- All critical-path tests must pass: approval denial/revocation, lifetime and batch scope, changed-diff invalidation, read-only SQL, sandbox boundaries and default network denial, cancellation, timeouts/retries, budget enforcement, secret redaction, and task-state consistency.
- Achieve at least 80% aggregate branch coverage across `domain/`, `application/`, and `security/`. `pytest-cov` and branch measurement are configured in `pyproject.toml`. Its `fail_under` checks combined statement/branch coverage; also inspect `covered_branches / num_branches` in the coverage JSON for the required branch-only gate. Latest run: 309/348 branches (88.79%), 103 passed, 3 opt-in live-container tests skipped.
- Provide adapter contract tests for OpenAI API, Gemini API, DeepSeek API, local Ollama, SQLite 3, PostgreSQL 16+, locally hosted Qdrant/Milvus/ChromaDB, and Brave Search API.
- Run desktop smoke tests on Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2. Include chat, settings, approvals, conversation viewing/resumption/deletion, and sandboxed command/test execution.
- Verify retention and credential handling: conversations remain until deleted, ordinary redacted logs expire after seven days, explicitly saved logs persist until deleted, temporary raw data is cleaned up, and unavailable credential stores trigger memory-only fallback.
- Deterministic automated checks must run without live credentials. Live-service and performance checks require explicit configuration and separate environment reporting.

## Workstream B Validation

Run `uv run pytest --cov --cov-report=term-missing --cov-report=json:/tmp/amethyst-coverage.json`, Ruff lint/format checks, `uv run mypy src tests`, and `uv build`. `tests/integration/test_agent_sandbox.py` covers the application/approval/sandbox/provider boundary with doubles. `test_live_sandbox.py` exercises real container boundaries, default network denial, exit reporting, output caps, timeouts, cancellation, and approval scope; it skips unless explicitly enabled. See `docs/sandbox_runtime.md` for profile prerequisites, report metadata, and commands.

The current development host is Ubuntu 22.04.5 with inaccessible Docker socket; real-container acceptance has not run. Ubuntu 24.04 and Windows 11/WSL2 results remain Pending. Desktop/adapter handoff checks are in `tests/integration/README.md`; they do not claim contributor review or completed A/C integration.

## Performance Acceptance

Measure p95 over at least 30 runs per tested reference configuration, recording hardware, OS, model/provider, and network conditions. A typical task uses at most three tool calls and 1,000 generated tokens. Exclude user-approval waits and report local-model cold starts separately.

- First visible model token: at most 10 seconds from request dispatch for streaming-capable models.
- Typical task: at most 120 seconds from submission to completion.
- UI status feedback: at most 200 milliseconds after a user action.

Verify configurable operational defaults and limit enforcement against requirements sections 5.5 and 5.6. Benchmark fixtures and reference configurations: `Pending`; these targets have not been measured yet.
