# Project

## Ten-Line Summary

1. The project aims to build an AI-assisted coding agent.
2. Users interact with the agent through a chat interface.
3. The agent can generate, inspect, and improve code within defined permissions.
4. It can use external resources such as SQL databases, web search, and vector stores.
5. A unified interface will configure models, connections, permissions, and skills.
6. Users retain control over connections, local access, and file modifications.
7. The system must present and enforce approvals for protected actions.
8. Reusable skills can be created and managed.
9. Full functional requirements are in `docs/project_requirements.md`.
10. Specific technologies and several acceptance criteria remain undecided.

## Objectives

- Meet the MVP and later requirements described in `docs/project_requirements.md`.
- Keep model providers, connectors, and skill management behind modular interfaces.
- Protect credentials, limit permissions, and make agent actions visible.

## Scope

### Included

- Agent chat, code generation, and code inspection.
- Configurable integrations for read-only SQL, web search, and vector retrieval.
- Skill, task, and permission management.
- Explicit approval workflows for file changes and high-impact actions.

### Excluded

- The suggested MVP/later classifications are not approved decisions; they remain proposals.
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

## Project Status

Requirements and an initial modular skeleton are available. Functional implementation and acceptance status: `Pending`.

## Related Repositories and Services

- Requirements: `docs/project_requirements.md`.
- Specific external services and related repositories: `Pending`.

## Minimal Glossary

- **System:** the complete application.
- **Agent:** the language-model-driven component that plans tasks and uses tools.
- **MVP / Later:** proposed delivery scope in the requirements, not yet approved as a product decision.
- **Connector:** an integration with an external resource.
- **Skill:** reusable instructions that a user can save and manage.
