# Conventions

## Principles

- Keep clear module boundaries for providers, connectors, skills, permissions, and agent execution.
- Apply least privilege and explicit approval for protected actions.
- Keep task, tool, and approval status visible.
- Treat `docs/project_requirements.md` as the normative requirements source.
- Write all project-authored code, identifiers, comments, documentation, and user-facing text in English.

## Repository Structure

The Python application lives in `src/1hack_amethyst/`: `application/` for use cases, `domain/` for core types, `ports/` for contracts, `adapters/` for integrations, `security/` for permissions, `skills/` for reusable skills, and `configuration/` for configuration. A standalone desktop GUI is approved; its framework, implementation, and location remain `Pending`. `src/llm/agent.py` is pre-existing code; migration or removal is `Pending`.

## Style and Standards

### Naming

- Use English for identifiers and user-facing text.
- Use `snake_case` for modules, functions, and variables; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants.
- Use short, descriptive kebab-case branch descriptions.

### Code Formatting

- Use four spaces for Python indentation and UTF-8 text files with LF line endings.
- Format Python with Ruff using an 88-character line length.
- Keep Markdown readable; do not enforce line wrapping automatically.

### Linting and Formatting

- Run `uv run ruff check .` for linting.
- Run `uv run ruff format --check .` to check formatting; use `uv run ruff format .` to format.
- Ruff rules: `E`, `F`, `I`, `UP`, and `B`.

## Dependency Management

Declare runtime dependencies in `[project].dependencies` and development tools in the `dev` dependency group in `pyproject.toml`. Use `uv` to synchronize and run project tools. Commit `uv.lock` so installations use the resolved dependency versions. Do not add dependencies without a project need.

## Common Errors to Avoid

- Do not couple agent logic directly to a specific provider or connector.
- Do not allow write queries through read-only SQL interfaces.
- Do not execute tools or modify files before required approval.
- Do not expose secrets in messages, logs, or errors.
- Do not add non-English project-authored content unless requested.

## Minimum Security

Apply requirements FR-26 through FR-30 and NFR-04 through NFR-07 in `docs/project_requirements.md`: scoped and revocable permissions, credential protection, data minimization, and blocking actions without required approval.

## Documentation

Write new and maintained project documentation in English. Document stable interfaces and decisions in context. Keep approved requirements distinct from recommendations. Preserve existing source documents unless explicitly asked to translate or rewrite them.

## Decisions That Must Not Be Broken

- Existing file modifications require explicit approval of the displayed diff, individually or in an explicitly listed batch; changed proposals require renewed approval (FR-27).
- Tool execution must be blocked when required approval is missing or revoked (FR-30).
- Providers, connectors, and skills must retain modular boundaries (NFR-11).
- Product commands/tests run in a container sandbox restricted to the approved workspace, with network disabled by default (FR-16, FR-17, NFR-06).
- Apply the approved limits, approval lifetimes, and retention rules in requirements section 5; do not treat documentation of these decisions as completed implementation.
