# Testing

## Framework and Layout

- Use `pytest`.
- Put unit tests under `tests/unit/` and integration tests under `tests/integration/`.
- Name test modules `test_<subject>.py` and test functions `test_<behavior>`.
- Keep tests independent and deterministic. Do not require live services or real credentials unless explicitly configured for an integration test.

## Commands

Shared offscreen Qt setup is in `tests/integration/conftest.py`. Fake services, deny-all/disabled adapters, and vendor fixtures are in `tests/support/`, outside the application wheel. `test_serialization.py` covers Unicode byte bounds and retrieval source alignment; `test_permissions_page.py` verifies exact grant, revocation, and diagnostic-retention commands after the UI extraction. Source and test functions follow Numpydoc and the 100-line maximum; see `docs/code_structure.md` for structure and cleanup checks.

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

`tests/integration/test_connection_page.py` verifies model/tool tab isolation, saved setting loading, typed options, preserved credential references, separate replacement secrets, and cross-category name protection. Model/tool adapter, runtime, and desktop regressions remain in their existing suites. This refactor preserves the storage schema and does not establish live-service or visible desktop acceptance.

`tests/unit/test_connection_settings.py` covers explicit model context sizes for all four providers, rejects invalid sizes, and preserves nested inline-secret rejection. Headless desktop workflows configure an explicit 8K Ollama context with 4K input and 2K output limits, covering the settings-to-adapter path that previously misclassified `context_tokens` as a credential.

Requirements section 5.8 defines the release gate; implementation and results remain `Pending`.

PydanticAI now owns the iterative tool cycle through the existing provider and dispatcher bridges. `ModelRunner` has a guarded compatibility path for exact textual `{name, arguments}` envelopes matching an enabled tool; deterministic coverage for message-history conversion, repeated tool calls, textual-envelope recovery, and token-use display remains `Pending`; no test result is implied by static checks.

- All critical-path tests must pass: approval denial/revocation, lifetime and batch scope, changed-diff invalidation, read-only SQL, sandbox boundaries and default network denial, cancellation, timeouts/retries, budget enforcement, secret redaction, and task-state consistency.
- Achieve at least 80% aggregate branch coverage across `domain/`, `application/`, and `security/`. `pytest-cov` and branch measurement are configured in `pyproject.toml`. Its `fail_under` checks combined statement/branch coverage; also inspect `covered_branches / num_branches` in the coverage JSON for the required branch-only gate. Integrated desktop run on Ubuntu 24.04.3 WSL, Python 3.13.18: 327/384 branches (85.16%), 92.32% combined coverage. Real-container tests remain opt-in.
- Provide adapter contract tests for OpenAI API, Gemini API, DeepSeek API, local Ollama, SQLite 3, PostgreSQL 16+, locally hosted Qdrant/Milvus/ChromaDB, and Brave Search API.
- Run desktop smoke tests on Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2. Include chat, settings, approvals, conversation viewing/resumption/deletion, and sandboxed command/test execution.
- Verify retention and credential handling: conversations remain until deleted, ordinary redacted logs expire after seven days, explicitly saved logs persist until deleted, temporary raw data is cleaned up, and unavailable credential stores trigger memory-only fallback.
- Deterministic automated checks must run without live credentials. Live-service and performance checks require explicit configuration and separate environment reporting.

## Workstream B Validation

Run `uv run pytest --cov --cov-report=term-missing --cov-report=json:/tmp/amethyst-coverage.json`, Ruff lint/format checks, `uv run mypy src tests`, and `uv build`. `tests/integration/test_agent_sandbox.py` covers the application/approval/sandbox/provider boundary with doubles. `test_live_sandbox.py` exercises real container boundaries, default network denial, exit reporting, output caps, timeouts, cancellation, and approval scope; it skips unless explicitly enabled. See `docs/sandbox_runtime.md` for profile prerequisites, report metadata, and commands.

The earlier Workstream B host was Ubuntu 22.04.5 with an inaccessible Docker socket. Integration checks now run under Ubuntu 24.04.3 WSL with Python 3.13.18 and Qt offscreen: the final run passed 124 tests and skipped three opt-in real-container tests, without warnings. `tests/integration/test_desktop.py` exercises the real desktop/agent/HTTP-adapter/SQLite boundary with local protocol fixtures; `tests/unit/test_runtime.py` covers connector aliases, vector-result normalization, settings retention, credential isolation, unavailable optional clients, and database handle cleanup. The focused native-Windows desktop/runtime run passed ten tests. The normal launcher is checked via `--version`, and the built wheel is checked in an isolated environment for imports, desktop modules, launcher, and packaged assets. See `docs/desktop_integration.md`. Real-container, live-service, visible native Ubuntu/WSLg, OS credential-store, and performance acceptance remain Pending.

## Repository Refactor Validation — 2026-11-14

The complete deterministic suite on WSL/Linux, Python 3.13.18, Qt offscreen passes **152 tests**, with **three opt-in real-container tests skipped**. Combined statement/branch coverage is **93.09%**; branch-only coverage is **313/364 (85.99%)**, above the approved 80% gate. Focused native-Windows settings, adapter, runtime, and permission/desktop checks also pass. Ruff lint/format, mypy with the Linux platform target, wheel/source build, and fresh extracted-wheel imports/CLI/PNG checks pass. The wheel excludes previews and `tests/support` doubles.

AST/reference checks confirm that source and test functions have Numpydoc sections and stay within 100 lines, and find no unreferenced private function names or repeated complete production function bodies. These are reference/structure checks, not proof about every possible dynamic call. Live vendor, real-container, visible desktop, OS credential-store, and performance acceptance remain Pending.

## Performance Acceptance

Measure p95 over at least 30 runs per tested reference configuration, recording hardware, OS, model/provider, and network conditions. A typical task uses at most three tool calls and 1,000 generated tokens. Exclude user-approval waits and report local-model cold starts separately.

- First visible model token: at most 10 seconds from request dispatch for streaming-capable models.
- Typical task: at most 120 seconds from submission to completion.
- UI status feedback: at most 200 milliseconds after a user action.

Verify configurable operational defaults and limit enforcement against requirements sections 5.5 and 5.6. Benchmark fixtures and reference configurations: `Pending`; these targets have not been measured yet.
