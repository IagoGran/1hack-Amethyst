# Architecture

## Overview

The product uses a standalone local PySide6 desktop and an in-process agent that coordinates models and tools. Supported platforms are Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2. `DesktopRuntime` composes application, security, adapters, and durable repositories; `DesktopWorker` owns one persistent asyncio loop on a Qt thread. The existing uv wheel backend packages the application; native installers remain `Pending`.

## Main Components

- Interface: `ui/desktop.py` connects the existing sidebar and transcript widgets to real services. Pages provide chat/model selection, connections, numeric limits, skills, permissions, diagnostics, and task details. History supports viewing/resumption/deletion; empty assistant placeholders are omitted from loaded history and removed after empty/failed turns. Exact-action/diff review, cancellation, token increases, and revocation are trusted UI controls. Conversation components live in `ui/conversation_page.py`, `message_card.py`, and `composer.py`; permissions/diagnostics have a dedicated page. Preview entry points have been removed.
- Application/agent: `src/amethyst/application/`; `AgentService` handles task/event orchestration, context/skill application, cancellation, deadlines, and bounded retries. PydanticAI `Agent` owns iterative tool orchestration through native OpenAI, Gemini, DeepSeek, and Ollama models constructed by `configuration/models.py`. The application layer streams text, reserves and accounts task tokens, pauses until an explicit budget increase, and persists translated conversation history. Registered tool functions delegate to `ToolDispatcher` for authorization, approval, limits, and result handling.
- Domain: `src/amethyst/domain/`; contains task states and shared request/result/event values in `contracts.py`.
- Contracts: `src/amethyst/ports/`; includes async application, model, tool/health, approval, repository, credential, and sandbox protocols. See `docs/s0_contract_baseline.md` for semantics and review status.
- Adapters: `src/amethyst/adapters/`; stdlib HTTP streaming adapters for OpenAI, Gemini, DeepSeek, and Ollama; SQLite read-only SQL; Brave Search; and Qdrant, Milvus, and Chroma vector adapters. PostgreSQL uses optional psycopg 3. External vector adapters use optional vendor clients. Contract tests are in `tests/unit/test_integrations.py`. Runtime/live-service acceptance remains pending.
- Permissions and approvals: `src/amethyst/security/`; session grants, exact-action/batch approvals, reviewed workspace diffs, credential fallback/redaction, and retention services are implemented. The deny-all double remains available under `tests/support/` for contract tests.
- Skills: SQLite-backed management in the desktop; the agent applies enabled skills when explicitly selected or matched by a literal `contains:` condition.
- Configuration: validated secret-free connection settings and adapter factories; `configuration/settings.py` persists numeric operational limits atomically in a database-adjacent JSON file. Credentials remain in the separate OS/memory store.
- Execution: `security/sandbox.py` implements Docker Engine/runc through a local Unix socket with a pinned image, read-only non-recursive workspace mount, default network denial, resource limits, and confirmed cleanup. Implicit image volumes are rejected; image health checks and daemon output logging are disabled. The adapter remains disabled until host validation; the fail-closed test double is isolated under `tests/support/disabled_sandbox.py`. See `docs/sandbox_runtime.md` for the selected profile and pending Ubuntu/WSL2 acceptance.
- Conversation, skill, and connection storage: durable repositories backed by an application-owned SQLite database. A version-1 schema stores JSON payloads and applies upserts, ordered listing, and idempotent deletion. The default path follows `XDG_DATA_HOME` or `~/.local/share/amethyst/amethyst.sqlite3`. Encryption, backup, cleanup scheduling, and recovery from future schema migrations remain `Pending`.
- Preview-only persistence and sample records have been removed. Test doubles and vendor fixtures live under `tests/support/` and are excluded from the application distribution.

## Data Flow

The desktop submits a task to its persistent worker loop. `DesktopRuntime` resolves the selected native PydanticAI model and enabled connectors, assigning distinct connector aliases and normalizing Brave/vector list results into bounded retrieval chunks. `AgentService` reloads retained messages, applies selected skills, and starts PydanticAI's iterative `Agent` loop. Structured provider tool calls remain tool calls; ordinary text is never promoted to an operation. The history converter omits unanswered calls persisted before a failed operation. PydanticAI invokes registered tools, whose functions pass through `ToolDispatcher` before execution. Qt renders text, token use/remaining budget, results, sources, task state, and exact approval proposals; it removes empty assistant placeholders after failed or empty turns. Trusted decisions return to the same worker loop. Task-budget exhaustion waits for an explicit increase. Shutdown awaits cancellation/cleanup before closing the worker. The available model-facing tools and their access rules are maintained in `docs/tool_inventory.md`. Headless desktop-to-adapter checks are in `tests/integration/test_desktop.py`; application-to-sandbox checks are in `test_agent_sandbox.py`. Live-service, real-container, visible desktop, and performance acceptance remain `Pending`.

## External Integrations

- Models: OpenAI API, Gemini API, DeepSeek API, and local Ollama models.
- Read-only external SQL: SQLite 3 and PostgreSQL 16+.
- Locally hosted vector stores: Qdrant, Milvus, and ChromaDB.
- Web search: Brave Search API.
- Shared model/tool/health contracts exist in `ports/`. Model adapters use the standard library; the approved optional external SQL/vector clients are declared as extras in `pyproject.toml`. Exact supported model IDs and per-model context windows remain `Pending`; adapters expose configurable context-token values and provider defaults.

## Key Architectural Decisions

- Keep modular interfaces for providers, connectors, and skills (NFR-11).
- Use PydanticAI `Agent` and native providers for the iterative model/tool loop; retain Amethyst budget, permission, approval, and connector boundaries.
- Separate permission checks from tool execution.
- Use a local standalone desktop deployment; server/hybrid deployment and host-local command execution are outside the approved initial scope.
- Bind edit approval to the reviewed diff and invalidate it when the proposal or relevant file state changes. Action/batch approval expires after execution or task completion; session read grants expire on app exit.
- Persist conversations until deleted. Expire redacted diagnostic logs after seven days unless explicitly saved permanently. See `ENVIRONMENT.md` and requirements section 5.7 for data handling.
- Use the OS credential store with a memory-only fallback; no plaintext disk fallback.
- Desktop framework: PySide6, declared as a runtime dependency. GUI/application calls use a persistent Qt worker loop and signals; `AsyncThread` owns shared loop cleanup. Embedding-model selection for natural-language vector queries remains `Pending`; vector tools accept numeric query vectors.
- Internal persistence engine: SQLite from Python's standard library, selected for the single-user local application. The database file receives best-effort POSIX mode `0600`; this is not encryption and may not set Windows ACLs.
- Container runtime/profile: Docker Engine/runc on a local Linux daemon; Ubuntu/WSL2 platform acceptance remains `Pending`. See `docs/sandbox_runtime.md`.

## Boundaries and Responsibilities

The repository-wide structure is documented in `docs/code_structure.md`. `AgentService` composes native PydanticAI execution and `ToolDispatcher`, with task-local values in `application/state.py`, budgets and timing in dedicated modules, and literal skill matching in `skills/selection.py`. HTTP provider adapters remain for health checks and protocol contracts; native provider models handle agent generation. SQL tools share `ReadOnlySQLTool` while retaining database-enforced restrictions. Generic repository contracts and record codecs avoid duplicated persistence logic. JSON record bounding uses one UTF-8-aware linear serializer. Docker transport, credential redaction, and approval lookup have separate modules; authorization policy remains in the security services.

Model and tool configuration now have independent validators and factories in `configuration/models.py` and `configuration/tools.py`. Immutable metadata in `configuration/catalog.py` supplies categories, public fields, and result shapes to validation, runtime composition, and desktop forms. `configuration/connections.py` preserves existing imports and the serialized connection schema. `ModelAdapter` shares provider setup/capabilities; the separate `Tool` superclass defines the built-in execution role. Connector aliases and result translation live in `application/tools.py`. Connections presents separate Models and Tools forms derived from `ConnectionEditor`. See `docs/integration_architecture.md` for the extension workflow; dynamic plugin registration remains Pending.

- The interface presents status, settings, results, and approval requests; it does not decide effective authorization by itself.
- The application layer orchestrates tasks and tools.
- Adapters implement contracts for external services.
- Authorization checks must happen before protected execution.

## Diagrams

N/A.
