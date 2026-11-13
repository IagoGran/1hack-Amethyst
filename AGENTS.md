# Repository Agent Instructions

## Mandatory Context Source

`.ai-context/` is the operational source of project context. For every task, before inspecting code or editing files, read `.ai-context/README.md` and the minimum relevant documents in the order it defines.

## Required Context Maintenance After Changes

After any change that affects scope, structure, interfaces, dependencies, configuration, conventions, or a project decision, update the relevant `.ai-context/` documents in the same change. Do not leave the context describing a structure or decision that has changed. For changes that do not affect those areas, check whether the context remains accurate and do not edit it without a reason.

## Working Rules

- Do not inspect code before reading the applicable context.
- Read only the files needed for the task; do not scan the entire repository by default.
- Do not invent decisions; mark unknowns as `Pending`.
- Use `docs/project_requirements.md` as the detailed requirements reference and preserve the distinction between requirements and recommendations.
- Respect applicable permissions and approvals, especially before modifying existing files or performing protected actions.
- Write all new code, comments, documentation, summaries, and user-facing text in English unless the user explicitly requests another language.

## Reading Order

Follow the order and document map in `.ai-context/README.md`. If a task changes the context or repository structure, update that map and the affected area guides as well.
