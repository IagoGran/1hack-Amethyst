# .ai-context

## Purpose

This directory is the project's context source for people and agents. It summarizes requirements and working rules without replacing `docs/project_requirements.md`, which remains the detailed requirements source.

## Key Rule

Before inspecting code or changing files, read this index and the minimum relevant documents for the task. Keep this context current when project knowledge changes; mark undecided items as `Pending`.

## Official Reading Order

1. `.ai-context/README.md`
2. `.ai-context/PROJECT.md`
3. `.ai-context/TASKING.md`
4. `.ai-context/CONVENTIONS.md`
5. `.ai-context/ARCHITECTURE.md` and `.ai-context/ENVIRONMENT.md`, when relevant
6. The affected area guide: `frontend/DEV.md` or `backend/DEV.md`
7. Relevant specialized documents, such as `TESTING.md`
8. Only the code required for the task

You do not need to read every document for every task. Do not inspect code until you have read the applicable context.

## How to Use This Context

- For scope or behavior changes, read `PROJECT.md` and `docs/project_requirements.md`.
- For planning and closing work, read `TASKING.md`.
- For repository-wide changes, read `CONVENTIONS.md` and `ARCHITECTURE.md`.
- For interface work, read `frontend/DEV.md`; for agent logic, providers, tools, permissions, or data, read `backend/DEV.md` and relevant backend documents.
- For configuration and secrets, read `ENVIRONMENT.md`.
- For test changes or validation, read `TESTING.md`.
- If implementation conflicts with a requirement, document it as `Pending` instead of inventing a decision.

## Document Map

### Core

- `PROJECT.md`: known purpose, approved acceptance scope, remaining recommendations, and implementation status.
- `TASKING.md`: workflow and definition of done.
- `CONVENTIONS.md`: repository-wide rules and structure.

### Common Documents

- `ARCHITECTURE.md`: planned modules, local desktop deployment, selected integrations, and pending implementation choices.
- `ENVIRONMENT.md`: supported platforms, operational defaults, retention, credential handling, and environment variables.

### Frontend

- `frontend/DEV.md`: interface development guide.
- `src/amethyst/ui/`: integrated PySide6 desktop, production conversation widgets, independent settings/permission pages, and persistent async worker. Preview launchers have been removed.

### Backend

- `backend/DEV.md`: agent and service development guide.

### Specialized Documents

- `TESTING.md`: test conventions and approved MVP acceptance and coverage gates.
- `docs/s0_contract_baseline.md`: implemented S0 interface proposals, fake behavior, branch integration, and pending technology decisions.
- `docs/implementation_plan.md`: three-person MVP tasks, branch ownership, dependency order, and requirement coverage.
- `docs/sandbox_runtime.md`: selected Docker runtime/profile, threat boundary, opt-in live tests, and pending platform acceptance.
- `docs/workstream_b_summary.md`: application/security composition guide and Workstream A/C integration boundaries.
- `docs/desktop_integration.md`: integrated A/B/C desktop launch, configuration, connector translation, async ownership, and pending acceptance.
- `docs/integration_architecture.md`: separate model/tool configuration, adapter superclasses, connection catalog, category-specific settings, and built-in extension workflow.
- `docs/code_structure.md`: repository-wide module boundaries, shared implementations, removal of previews, test-only support, and validation workflow.

## Maintenance Rules

- Update context in the same change that alters scope, modules, interfaces, configuration, or conventions.
- Treat `docs/project_requirements.md` as the normative requirements reference.
- Section 5 of `docs/project_requirements.md` records approved acceptance decisions. Keep other proposed MVP boundaries and Added requirements distinct from those approvals.
- Use `Pending` for undecided items and `N/A` only when something does not apply.
- Write new project code and documentation in English.

## Context Versioning

Standard: `context_standard: v1`. Update affected documents together with the knowledge they describe; content changes do not require changing this version.

## Context Owners

Owner: `Pending`.

---

## Standard Version

context_standard: v1
