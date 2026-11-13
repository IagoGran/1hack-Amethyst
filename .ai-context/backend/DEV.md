# Backend Development

## Backend Stack

Python 3.13+ with standard-library DTOs and async protocols; runtime vendor dependencies remain `Pending`. The distribution/CLI is `1hack-amethyst`; Python imports use `amethyst`.

## Directory Structure

The package is `src/amethyst/`, divided into `application/`, `domain/`, `ports/`, `adapters/`, `security/`, `skills/`, and `configuration/`. Integration choices are approved below; adapter implementations remain pending.

## Local Development

Install runtime and development dependencies with `uv sync --group dev`, then start the provisional CLI with `uv run 1hack-amethyst`.

## Build and Packaging

Build the package with `uv build`. The build backend maps the distribution to `src/amethyst/`; `uv run python -m amethyst` and `uv run 1hack-amethyst` use the same provisional launcher.

## Environment Variables

See `.ai-context/ENVIRONMENT.md`. Do not include secret values.

## Endpoints and Interfaces

S0 async contracts are in `src/amethyst/ports/`, with shared DTOs in `domain/contracts.py`. See `docs/s0_contract_baseline.md` for stream/error/cancellation semantics, approvals, repositories, credential references, and sandbox invocation. `adapters/fakes.py` provides deterministic development doubles; approval and sandbox placeholders fail closed. GUI transport and live-service acceptance remain `Pending`.

Provider adapters use the standard-library HTTP client and stream SSE/NDJSON. PostgreSQL and vector-store clients are optional dependencies declared in the `postgresql`, `qdrant`, `chroma`, `milvus`, and combined `integrations` extras. Install them with `uv sync --extra integrations` when using all adapters. Model IDs, exact per-model context windows, SDK versions, and live-service results remain `Pending`.

Commands and tests must execute in a container sandbox restricted to the approved workspace, with network access disabled by default. Host-local execution is outside the approved initial scope. The `Sandbox` protocol and disabled placeholder exist. Container runtime and production enforcement: `Pending`.

## Data and Persistence

Conversation, skill, and connection repository contracts have detached in-memory doubles and SQLite durable implementations in `adapters/persistence.py`. The application database path defaults to `$XDG_DATA_HOME/amethyst/amethyst.sqlite3`, or `~/.local/share/amethyst/amethyst.sqlite3`. Stored records use JSON payloads in schema version 1, and the database file receives best-effort POSIX mode `0600`. Encryption, backup, migration beyond version 1, and cleanup scheduling remain `Pending`. User SQL in the requirements refers to an external read-only tool and does not select this internal SQLite database.

Conversations persist locally until deleted, with MVP viewing/resumption/deletion. Settings and skills remain until deleted. Raw retrieval/workspace copies are discarded after each task unless explicitly saved; conversation content follows conversation retention. Redacted diagnostic logs expire after seven days unless explicitly saved permanently. Credentials use the OS credential store with a memory-only fallback. See requirements section 5.7 and `.ai-context/ENVIRONMENT.md` for complete rules.

## Approval and Resource Enforcement

- Authorize a single protected action or an explicitly listed batch; existing-file changes require reviewed diffs and renewed approval after invalidating changes.
- Consume approval on execution and expire it no later than task completion. Read-only session grants end on app exit; revocation blocks further protected actions.
- Enforce the configurable time, token, retrieval, result-size, and retry defaults in requirements sections 5.5 and 5.6. Pause at the task token budget until explicitly increased.
- Retry only transient failures, at most twice after the initial attempt; never automatically repeat file mutations or commands with uncertain outcomes.
- Enforcement implementation: `Pending`.

## Debugging

Tools and workflow: `Pending`.

## Backend-Specific Conventions

See `.ai-context/CONVENTIONS.md` and `.ai-context/TESTING.md`.

## Backend Change Checklist

- [ ] Keep providers and connectors decoupled through contracts.
- [ ] Check authorization before executing protected tools.
- [ ] Restrict SQL queries to read-only where applicable.
- [ ] Protect credentials and minimize transmitted data.
- [ ] Update context when interfaces, persistence, or configuration change.
