# Work and Tasks

## Work Types

### Bug Fix

Use relevant context to locate the issue, make the smallest necessary change, and report the result. Specific criteria: `Pending`.

### Feature

Link the change to relevant requirements, define modular boundaries, and update context when decisions or structure change.

### Refactor

Preserve agreed behavior and module boundaries; document structural changes in the relevant context.

### Documentation

Keep documentation consistent with requirements and actual project status. Do not turn recommendations into decisions.

## Workflow

### Branches

Use `<type>/<short-kebab-case-description>`, for example `feature/tool-approval`, `fix/task-cancellation`, `docs/context-guide`, or `refactor/provider-ports`.

For the three-person MVP implementation, use the ownership, branch names, task breakdown, shared-contract workflow, and dependencies in `docs/implementation_plan.md`. The current ownership is Iago (Person A / Workstream A), Hugo (Person B / Workstream B), and Antonio (Person C / Workstream C). The owner confirmed `dev` as the integration branch for S0, implemented on `feature/contracts` and merged after checks pass. Planned workstream branches are `feature/mvp-desktop`, `feature/mvp-agent-security`, and `feature/mvp-integrations`; preserve existing differently named branches. Keep workstream PRs independently mergeable; coordinate shared contracts before cross-branch implementation.

### Commits

Use Conventional Commits: `<type>(<optional-scope>): <imperative summary>`, written in English. Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, and `chore`.

### Pull Requests

Use an English title and description. Summarize behavior, link relevant requirements, note context updates, and report validation. Additional repository-specific policy: `Pending`.

## Definition of Done

- The change meets its objective and does not contradict `docs/project_requirements.md`.
- Every Python function meets the 100-line maximum and has a Numpydoc docstring with purpose, parameters, return value, and relevant notes.
- Relevant `.ai-context/` documents are up to date.
- New code, comments, documentation, commit messages, and user-facing text are in English.
- The result and any undecided items are reported.
- Run checks when requested or explicitly included in the agreed workflow.
- For MVP feature work, follow `docs/implementation_plan.md` and keep requirement coverage and ownership current as tasks are completed or reassigned.

## General Task Checklist

- [ ] Read `.ai-context/README.md` and the minimum relevant context before inspecting code.
- [ ] Check applicable requirements and existing task state.
- [ ] Keep the change modular and within granted permissions.
- [ ] Update context when the change alters documented knowledge.
- [ ] Report changes and validation performed.

## Asking an Agent for Help

### Minimum Input

Goal, expected behavior, and known constraints. For functional changes, reference applicable requirements.

### Expected Output (Summary and Checklist)

Summary of affected files and behavior, undecided items, and validation performed.

## Limits and Things to Avoid

- Do not read code before consuming relevant context.
- Do not invent providers, contracts, policies, or technical decisions.
- Do not bypass approvals required for protected actions.
- Do not store or expose secrets in documentation, output, or logs.
