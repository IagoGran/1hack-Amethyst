# Architecture

## Overview

The product requires a standalone, local, single-user desktop chat interface and an agent component that coordinates models and tools. Supported platforms are Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2. The initial structure separates the interface, application orchestration, domain, contracts, and integrations. Desktop framework, packaging, and internal process topology remain `Pending`.

## Main Components

- Interface: standalone desktop window with chat, task status, settings, approvals, and conversation viewing/resumption/deletion. Stack and location: `Pending`.
- Application/agent: `src/amethyst/application/`; evaluation, planning, and orchestration remain to be implemented.
- Domain: `src/amethyst/domain/`; contains task states and shared request/result/event values in `contracts.py`.
- Contracts: `src/amethyst/ports/`; includes async application, model, tool/health, approval, repository, credential, and sandbox protocols. See `docs/s0_contract_baseline.md` for semantics and review status.
- Adapters: `src/amethyst/adapters/`; placeholders for models and tools. Provider choices are approved below; adapter implementation remains pending.
- Permissions and approvals: `src/amethyst/security/`; deny-all placeholder available; production policy implementation pending.
- Skills: `src/amethyst/skills/`; persistence and management pending.
- Configuration: `src/amethyst/configuration/`; loading and validation pending.
- Execution: approved MVP container sandbox restricted to the workspace, with network disabled by default. `ports/sandbox.py` defines invocation; `adapters/sandbox.py` always refuses execution. Runtime and production implementation: `Pending`.
- Conversation storage: local persistence until user deletion is approved; repository contracts and in-memory development doubles exist. Durable storage engine and implementation: `Pending`.

## Data Flow

The user submits a task; the agent inspects relevant context, plans when needed, and requests required approvals for one action or an explicitly listed batch. Once authorized, it executes enabled tools within the configured limits, inspects results, and reports status and available sources. Task-budget exhaustion pauses work for an explicit increase. The S0 logical boundary uses async calls and typed, sequenced task events. GUI transport/event-loop integration and durable persistence remain `Pending`.

## External Integrations

- Models: OpenAI API, Gemini API, DeepSeek API, and local Ollama models.
- Read-only external SQL: SQLite 3 and PostgreSQL 16+.
- Locally hosted vector stores: Qdrant, Milvus, and ChromaDB.
- Web search: Brave Search API.
- Shared model/tool/health contracts exist in `ports/`; exact SDKs, model IDs, and provider-specific configuration validation remain `Pending`.

## Key Architectural Decisions

- Keep modular interfaces for providers, connectors, and skills (NFR-11).
- Separate permission checks from tool execution.
- Use a local standalone desktop deployment; server/hybrid deployment and host-local command execution are outside the approved initial scope.
- Bind edit approval to the reviewed diff and invalidate it when the proposal or relevant file state changes. Action/batch approval expires after execution or task completion; session read grants expire on app exit.
- Persist conversations until deleted. Expire redacted diagnostic logs after seven days unless explicitly saved permanently. See `ENVIRONMENT.md` and requirements section 5.7 for data handling.
- Use the OS credential store with a memory-only fallback; no plaintext disk fallback.
- Desktop framework, internal storage engine, container runtime, GUI transport, and durable persistence implementation: `Pending`.

## Boundaries and Responsibilities

- The interface presents status, settings, results, and approval requests; it does not decide effective authorization by itself.
- The application layer orchestrates tasks and tools.
- Adapters implement contracts for external services.
- Authorization checks must happen before protected execution.

## Diagrams

N/A.
