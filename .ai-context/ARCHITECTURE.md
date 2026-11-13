# Architecture

## Overview

The product requires a standalone, local, single-user desktop chat interface and an agent component that coordinates models and tools. Supported platforms are Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2. The initial structure separates the interface, application orchestration, domain, contracts, and integrations. Desktop framework, packaging, and internal process topology remain `Pending`.

## Main Components

- Interface: standalone desktop window with chat, task status, settings, approvals, and conversation viewing/resumption/deletion. Stack and location: `Pending`.
- Application/agent: `src/1hack_amethyst/application/`; evaluation, planning, and orchestration remain to be implemented.
- Domain: `src/1hack_amethyst/domain/`; contains the minimal `Task` type and status.
- Contracts: `src/1hack_amethyst/ports/`; includes initial model-provider and tool interfaces.
- Adapters: `src/1hack_amethyst/adapters/`; placeholders for models and tools. Provider choices are approved below; adapter implementation remains pending.
- Permissions and approvals: `src/1hack_amethyst/security/`; implementation pending.
- Skills: `src/1hack_amethyst/skills/`; persistence and management pending.
- Configuration: `src/1hack_amethyst/configuration/`; loading and validation pending.
- Execution: approved MVP container sandbox restricted to the workspace, with network disabled by default. Runtime, module location, and implementation: `Pending`.
- Conversation storage: local persistence until user deletion is approved; storage engine and implementation: `Pending`.

## Data Flow

The user submits a task; the agent inspects relevant context, plans when needed, and requests required approvals for one action or an explicitly listed batch. Once authorized, it executes enabled tools within the configured limits, inspects results, and reports status and available sources. Task-budget exhaustion pauses work for an explicit increase. Transport and persistence implementation details are `Pending`.

## External Integrations

- Models: OpenAI API, Gemini API, DeepSeek API, and local Ollama models.
- Read-only external SQL: SQLite 3 and PostgreSQL 16+.
- Locally hosted vector stores: Qdrant, Milvus, and ChromaDB.
- Web search: Brave Search API.
- Exact SDKs, model IDs, and adapter contracts: `Pending`.

## Key Architectural Decisions

- Keep modular interfaces for providers, connectors, and skills (NFR-11).
- Separate permission checks from tool execution.
- Use a local standalone desktop deployment; server/hybrid deployment and host-local command execution are outside the approved initial scope.
- Bind edit approval to the reviewed diff and invalidate it when the proposal or relevant file state changes. Action/batch approval expires after execution or task completion; session read grants expire on app exit.
- Persist conversations until deleted. Expire redacted diagnostic logs after seven days unless explicitly saved permanently. See `ENVIRONMENT.md` and requirements section 5.7 for data handling.
- Use the OS credential store with a memory-only fallback; no plaintext disk fallback.
- Desktop framework, internal storage engine, container runtime, APIs, and persistence implementation: `Pending`.

## Boundaries and Responsibilities

- The interface presents status, settings, results, and approval requests; it does not decide effective authorization by itself.
- The application layer orchestrates tasks and tools.
- Adapters implement contracts for external services.
- Authorization checks must happen before protected execution.

## Diagrams

N/A.
