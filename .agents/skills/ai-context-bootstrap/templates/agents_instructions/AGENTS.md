# Agent Operating Rules (Project-wide)

## Source of truth: `.ai-context/`

This repository uses a standardized context system in `.ai-context/`.

### Required reading order

Agents MUST follow the reading order defined in:

- `.ai-context/README.md`

### Non-negotiable rules

- Agents MUST NOT read source code before consuming `.ai-context/README.md` (and the minimum relevant context docs).
- Agents MUST read only what is necessary for the task (do not scan the whole repo).
- Agents MUST NOT invent project facts. Use `N/A` or `Pending` when unknown.

### How to proceed on a task

1. Read `.ai-context/README.md`
2. Read only the relevant docs for the task (backend/frontend/common)
3. If context is missing, propose updates to `.ai-context/` (minimal changes)
4. Only then inspect code if required

## Tool-specific adapters

If tool-specific instructions exist (e.g. `.github/copilot-instructions.md`), they must be consistent with this document and `.ai-context/README.md`.

## Language policy

- All agents MUST communicate with the user in Spanish.
- All generated content (reports, documentation, comments, summaries, files, etc.) MUST be written in Spanish.
- This applies by default to all interactions and outputs.

### Exception

- Only switch to another language if the user explicitly requests it.
