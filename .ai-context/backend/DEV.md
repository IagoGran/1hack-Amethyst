# Backend Development

## Backend Stack

Python 3.13+ with standard-library DTOs and async protocols. `keyring` supplies the explicitly selected Linux Secret Service backend; optional connector clients are declared as integration extras. PySide6 supplies the desktop runtime. The distribution/CLI is `1hack-amethyst`; Python imports use `amethyst`.

## Directory Structure

See `docs/code_structure.md` for the repository-wide module map. Keep orchestration, model execution, tool authorization/dispatch, budgets, and timing separate. `adapters/codecs.py` owns record serialization, `serialization.py` owns bounded JSON record encoding, and test-only implementations live in `tests/support/`. Public compatibility exports remain where documented; removed preview paths are intentionally unsupported.

The package is `src/amethyst/`, divided into `application/`, `domain/`, `ports/`, `adapters/`, `security/`, `skills/`, `configuration/`, and `ui/`. Provider/connector adapters and durable repositories are implemented. `application/runtime.py` composes them with the agent and security services for the desktop.

## Local Development

Install runtime and development dependencies with `uv sync --group dev`, then start the integrated desktop with `uv run 1hack-amethyst`. See `docs/desktop_integration.md` for configuration and optional connector extras.

## Build and Packaging

Build the package with `uv build`. The build backend maps the distribution to `src/amethyst/`; `uv run python -m amethyst` and `uv run 1hack-amethyst` launch the same PySide6 desktop. `--version` and `--help` work without initializing Qt or opening application data.

## Environment Variables

See `.ai-context/ENVIRONMENT.md`. Do not include secret values.

## Endpoints and Interfaces

S0 async contracts are in `src/amethyst/ports/`, with shared DTOs in `domain/contracts.py`. See `docs/s0_contract_baseline.md` for semantics, `docs/workstream_b_summary.md` for agent/security services, and `docs/desktop_integration.md` for A/B/C composition. `DesktopRuntime` normalizes tool names and retrieval result shapes without changing shared contracts. All application state and async operations stay on the persistent desktop worker loop. Fake and fail-closed implementations are test-only dependencies in `tests/support/`; they are not distributed with the application. Live provider/connector, real-container, and visible platform acceptance remain `Pending`.

Provider adapters use the standard-library HTTP client and stream SSE/NDJSON. PostgreSQL and vector-store clients are optional dependencies declared in the `postgresql`, `qdrant`, `chroma`, `milvus`, and combined `integrations` extras. Install them with `uv sync --extra integrations` when using all adapters. Model IDs, exact per-model context windows, SDK versions, and live-service results remain `Pending`.

Commands and tests use `security.sandbox.DockerSandbox`, with Docker Engine/runc, a local Unix socket, and a trusted digest-pinned image. The workspace is read-only, network is denied by default, implicit image volumes are rejected, daemon output logging and image health checks are disabled, and cleanup/terminal state are confirmed. Host-local fallback is absent. Runtime remains disabled until host validation; Ubuntu 24.04 and Windows/WSL2 acceptance are Pending. Read `docs/sandbox_runtime.md` before configuring or changing this boundary.

## Data and Persistence

Conversation, skill, and connection repository contracts have detached in-memory doubles and SQLite durable implementations in `adapters/persistence.py`. The application database path defaults to `$XDG_DATA_HOME/amethyst/amethyst.sqlite3`, or `~/.local/share/amethyst/amethyst.sqlite3`. Stored records use JSON payloads in schema version 1, and the database file receives best-effort POSIX mode `0600`. Encryption, backup, migration beyond version 1, and cleanup scheduling remain `Pending`. User SQL in the requirements refers to an external read-only tool and does not select this internal SQLite database.

Conversations persist locally until deleted, with MVP viewing/resumption/deletion. Settings and skills remain until deleted. Raw retrieval/workspace copies are discarded after each task unless explicitly saved; conversation content follows conversation retention. Redacted diagnostic logs expire after seven days unless explicitly saved permanently. Credentials use the OS credential store with a memory-only fallback. See requirements section 5.7 and `.ai-context/ENVIRONMENT.md` for complete rules.

## Approval and Resource Enforcement

- Authorize a single protected action or an explicitly listed batch; existing-file changes require reviewed diffs and renewed approval after invalidating changes.
- Consume approval on execution and expire it no later than task completion. Read-only session grants end on app exit; revocation blocks further protected actions.
- Enforce the configurable time, token, retrieval, result-size, and retry defaults in requirements sections 5.5 and 5.6. Pause at the task token budget until explicitly increased.
- Retry only transient failures, at most twice after the initial attempt; never automatically repeat file mutations or commands with uncertain outcomes.
- Enforcement is implemented in `application/limits.py`, `configuration/limits.py`, and `security/`. A/B/C composition is implemented; deterministic and headless desktop tests exercise it. Live-service, real-container, visible platform, and performance acceptance remain Pending.

## Debugging

Tools and workflow: `Pending`.

## Backend-Specific Conventions

Keep model configuration in `configuration/models.py` and resource-tool configuration in `configuration/tools.py`; share only public metadata and validation helpers. Built-in adapters derive from `ModelAdapter` or `Tool`, respectively, while application injection continues to use structural ports. Register built-ins through the catalog and the matching factory table. Preserve persisted connection kinds and credential references. See `docs/integration_architecture.md` before adding an integration.

See `.ai-context/CONVENTIONS.md` and `.ai-context/TESTING.md`.

## Backend Change Checklist

- [ ] Keep providers and connectors decoupled through contracts.
- [ ] Check authorization before executing protected tools.
- [ ] Restrict SQL queries to read-only where applicable.
- [ ] Protect credentials and minimize transmitted data.
- [ ] Update context when interfaces, persistence, or configuration change.
