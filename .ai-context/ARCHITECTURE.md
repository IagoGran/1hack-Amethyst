# Architecture

## Overview

The product requires a chat interface and an agent component that coordinates models and tools. The initial structure separates the interface, application orchestration, domain, contracts, and integrations. Deployment and topology remain `Pending`.

## Main Components

- Interface: chat, task status, settings, and approvals. Stack and location: `Pending`.
- Application/agent: `src/1hack_amethyst/application/`; evaluation, planning, and orchestration remain to be implemented.
- Domain: `src/1hack_amethyst/domain/`; contains the minimal `Task` type and status.
- Contracts: `src/1hack_amethyst/ports/`; includes initial model-provider and tool interfaces.
- Adapters: `src/1hack_amethyst/adapters/`; placeholders for models and tools. Specific providers: `Pending`.
- Permissions and approvals: `src/1hack_amethyst/security/`; implementation pending.
- Skills: `src/1hack_amethyst/skills/`; persistence and management pending.
- Configuration: `src/1hack_amethyst/configuration/`; loading and validation pending.

## Data Flow

The user submits a task; the agent inspects relevant context, plans when needed, and requests required approvals. Once authorized, it executes enabled tools, inspects results, and reports status and available sources. Transport and persistence details are `Pending`.

## External Integrations

Requirements include language models, SQL databases, web search, and vector stores. Specific services and protocols: `Pending`.

## Key Architectural Decisions

- Keep modular interfaces for providers, connectors, and skills (NFR-11).
- Separate permission checks from tool execution.
- Technologies, APIs, and persistence strategy: `Pending`.

## Boundaries and Responsibilities

- The interface presents status, settings, results, and approval requests; it does not decide effective authorization by itself.
- The application layer orchestrates tasks and tools.
- Adapters implement contracts for external services.
- Authorization checks must happen before protected execution.

## Diagrams

N/A.
