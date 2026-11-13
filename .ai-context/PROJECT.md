# Project

## Ten-Line Summary

1. The project aims to build an AI-assisted coding agent.
2. Users interact through a standalone, local, single-user desktop chat application.
3. The agent can generate, inspect, and improve code within defined permissions.
4. It can use external resources such as SQL databases, web search, and vector stores.
5. A unified interface will configure models, connections, permissions, and skills.
6. Users retain control over connections, local access, and file modifications.
7. The system must present and enforce approvals for protected actions.
8. Reusable skills can be created and managed.
9. Full functional requirements are in `docs/project_requirements.md`.
10. Acceptance criteria were approved on 2026-11-13; implementation technologies and acceptance results remain pending.

## Objectives

- Meet the approved acceptance baseline in section 5 of `docs/project_requirements.md`; keep remaining MVP/later recommendations distinct from approved decisions.
- Keep model providers, connectors, and skill management behind modular interfaces.
- Protect credentials, limit permissions, and make agent actions visible.

## Scope

### Included

- Agent chat, code generation, and code inspection.
- Configurable integrations for read-only SQL, web search, and vector retrieval.
- Skill, task, and permission management.
- Explicit approval workflows for file changes and high-impact actions.
- Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2, with a standalone desktop window.
- OpenAI API, Gemini API, DeepSeek API, and local Ollama models.
- Read-only SQLite 3 and PostgreSQL 16+; locally hosted Qdrant, Milvus, and ChromaDB; Brave Search API.
- MVP container-sandboxed commands and tests, restricted to the approved workspace, with network access disabled by default.
- MVP conversation viewing, resumption, and deletion; conversations persist until deleted.

These approved choices constrain the scope above; unrelated recommendations have not been approved implicitly.

### Excluded

- Server/hybrid application deployment and host-local command execution are outside the approved initial scope.
- Richer action history, extensible connector registration, broader model-parameter controls, and portable configuration remain later-release recommendations.
- Other exclusions: `Pending`.

## Users and Stakeholders

- People configuring and using the agent: as described in the requirements.
- Product owner and technical leads: `Pending`.

## Main Use Cases

- Chat with the agent and receive incremental output when supported by the model.
- Request code generation, inspection, debugging, and approved code changes.
- Configure and authorize models and data connectors.
- Query data through authorized tools and see available source attribution.
- Create and manage reusable skills.
- Resume or delete retained conversations and run authorized commands/tests in the workspace sandbox.

## Project Status

Requirements and an initial modular skeleton are available. Section 5 acceptance decisions are approved, including operational limits, retention, approvals, and the MVP testing gate. Functional implementation and acceptance results: `Pending`. Documentation of a decision is not evidence of implemented behavior.

## Related Repositories and Services

- Requirements: `docs/project_requirements.md`.
- Approved external integrations: OpenAI API, Gemini API, DeepSeek API, local Ollama, SQLite 3, PostgreSQL 16+, local Qdrant/Milvus/ChromaDB, and Brave Search API.
- Environment-specific endpoints, model IDs, and related repositories: `Pending`.

## Minimal Glossary

- **System:** the complete application.
- **Agent:** the language-model-driven component that plans tasks and uses tools.
- **MVP / Later:** delivery classifications that remain recommendations except where explicitly approved in requirements section 5.
- **Connector:** an integration with an external resource.
- **Skill:** reusable instructions that a user can save and manage.
