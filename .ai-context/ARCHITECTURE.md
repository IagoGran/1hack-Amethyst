# Architecture

## Overview

The product requires a standalone, local, single-user desktop chat interface and an agent component that coordinates models and tools. Supported platforms are Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2. The initial structure separates the interface, application orchestration, domain, contracts, and integrations. Desktop framework, packaging, and internal process topology remain `Pending`.

## Main Components

- Interface: standalone desktop window with chat, task status, settings, approvals, and conversation viewing/resumption/deletion. Exploratory PySide6 A1/A2/A3 previews live in `src/amethyst/ui/`; A3 exposes recent chats and a collapsible all-chats sidebar list that fills available sidebar space, scrolls as needed, highlights the active chat, and supports confirmed context-menu deletion. It exercises conversation history through `ConversationRepository` and a preview-only SQLite adapter with fictional sample conversations. Production framework and location remain `Pending`.
- Application/agent: `src/amethyst/application/`; `AgentService` implements task/event orchestration, context/skill application, tool selection, approval waits, cancellation, budgets, deadlines, and bounded retry/result handling through injected ports.
- Domain: `src/amethyst/domain/`; contains task states and shared request/result/event values in `contracts.py`.
- Contracts: `src/amethyst/ports/`; includes async application, model, tool/health, approval, repository, credential, and sandbox protocols. See `docs/s0_contract_baseline.md` for semantics and review status.
- Adapters: `src/amethyst/adapters/`; stdlib HTTP streaming adapters for OpenAI, Gemini, DeepSeek, and Ollama; SQLite read-only SQL; Brave Search; and Qdrant, Milvus, and Chroma vector adapters. PostgreSQL uses optional psycopg 3. External vector adapters use optional vendor clients. Contract tests are in `tests/unit/test_integrations.py`. Runtime/live-service acceptance remains pending.
- Permissions and approvals: `src/amethyst/security/`; session grants, exact-action/batch approvals, reviewed workspace diffs, credential fallback/redaction, and retention services are implemented. The deny-all S0 placeholder remains available.
- Skills: `src/amethyst/skills/`; skill persistence is provided by the SQLite repository; skill management/application remains pending.
- Configuration: `src/amethyst/configuration/`; provider/connector connection validation and adapter factories are implemented. General application settings loading remains pending.
- Execution: `security/sandbox.py` implements Docker Engine/runc through a local Unix socket with a pinned image, read-only non-recursive workspace mount, default network denial, resource limits, and confirmed cleanup. Implicit image volumes are rejected; image health checks and daemon output logging are disabled. The adapter remains disabled until host validation; `adapters/sandbox.py` is the S0 fail-closed placeholder. See `docs/sandbox_runtime.md` for the selected profile and pending Ubuntu/WSL2 acceptance.
- Conversation, skill, and connection storage: durable repositories backed by an application-owned SQLite database. A version-1 schema stores JSON payloads and applies upserts, ordered listing, and idempotent deletion. The default path follows `XDG_DATA_HOME` or `~/.local/share/amethyst/amethyst.sqlite3`. Encryption, backup, cleanup scheduling, and recovery from future schema migrations remain `Pending`.
- A3's preview-only SQLite adapter uses fictional sample conversations; production conversation persistence is provided by the durable repository described above.

## Data Flow

The user submits a task; `AgentService` inspects available context, plans before consequential actions, and requests required approval for one action or an explicitly listed batch. Once authorized, it executes enabled tools within configured limits, inspects results, and reports status and available sources through async calls and typed, sequenced events. Task-budget exhaustion pauses work for an explicit increase. The deterministic application-to-sandbox handoff is tested in `tests/integration/test_agent_sandbox.py`. GUI event-loop integration, live-service validation, and target-platform acceptance remain `Pending`.
## Data Flow

The user submits a task; `AgentService` inspects available context, plans before consequential actions, and requests required approval for one action or an explicitly listed batch. Once authorized, it executes enabled tools within configured limits, inspects results, and reports status and available sources through async calls and typed, sequenced events. Task-budget exhaustion pauses work for an explicit increase. The deterministic application-to-sandbox handoff is tested in `tests/integration/test_agent_sandbox.py`. A1–A3 previews bridge async calls through worker threads; production GUI event-loop integration, live-service validation, and target-platform acceptance remain `Pending`.

## External Integrations

- Models: OpenAI API, Gemini API, DeepSeek API, and local Ollama models.
- Read-only external SQL: SQLite 3 and PostgreSQL 16+.
- Locally hosted vector stores: Qdrant, Milvus, and ChromaDB.
- Web search: Brave Search API.
- Shared model/tool/health contracts exist in `ports/`. Model adapters use the standard library; the approved optional external SQL/vector clients are declared as extras in `pyproject.toml`. Exact supported model IDs and per-model context windows remain `Pending`; adapters expose configurable context-token values and provider defaults.

## Key Architectural Decisions

- Keep modular interfaces for providers, connectors, and skills (NFR-11).
- Separate permission checks from tool execution.
- Use a local standalone desktop deployment; server/hybrid deployment and host-local command execution are outside the approved initial scope.
- Bind edit approval to the reviewed diff and invalidate it when the proposal or relevant file state changes. Action/batch approval expires after execution or task completion; session read grants expire on app exit.
- Persist conversations until deleted. Expire redacted diagnostic logs after seven days unless explicitly saved permanently. See `ENVIRONMENT.md` and requirements section 5.7 for data handling.
- Use the OS credential store with a memory-only fallback; no plaintext disk fallback.
- Desktop framework, GUI transport, and embedding-model selection for converting retrieval queries to vectors: `Pending`.
- Internal persistence engine: SQLite from Python's standard library, selected for the single-user local application. The database file receives best-effort POSIX mode `0600`; this is not encryption and may not set Windows ACLs.
- Container runtime/profile: Docker Engine/runc on a local Linux daemon; Ubuntu/WSL2 platform acceptance remains `Pending`. See `docs/sandbox_runtime.md`.

## Boundaries and Responsibilities

- The interface presents status, settings, results, and approval requests; it does not decide effective authorization by itself.
- The application layer orchestrates tasks and tools.
- Adapters implement contracts for external services.
- Authorization checks must happen before protected execution.

## Diagrams

N/A.
