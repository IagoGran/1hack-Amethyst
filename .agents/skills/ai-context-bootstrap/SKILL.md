---
name: ai-context-bootstrap
description: Create and maintain `.ai-context/` without reading project code first.
---

# Skill: AI Context Bootstrap & Alignment

## Mission

Create, review and align `.ai-context/` for a software project using a provider-agnostic standard.
This skill exists to reduce cognitive load, avoid reading the full repository, and prevent invented context.

## Non-negotiable rules

- NEVER read project source code before reading `.ai-context/README.md`.
- `.ai-context/README.md` is the entry point and defines the reading order.
- Only read documents strictly relevant to the task.
- Do not invent facts. Use `N/A` or `Pending`.
- Do not delete or rewrite user content.
- Language rules:
  - Default language is Spanish.
  - Communicate with the user in Spanish.
  - Generate all outputs (documentation, comments, summaries, code comments, reports) in Spanish.
  - Do not switch language unless the user **explicitly** requests it.

## Scope

This skill:

- Creates CORE context files if missing
- Creates COMMON context files only when signals apply
- Aligns headings with the standard (L1)
- Suggests improvements but does not enforce content

This skill does NOT:

- Rewrite documentation
- Infer architecture from code
- Enforce opinions or best practices

## Workflow

1. Check if `.ai-context/README.md` exists.
2. If missing:
   - Create `.ai-context/`
   - Use rules/creation.md for creation decisions.
   - Create files using templates.
3. Detect project signals (see rules/signals.md).
4. Create COMMON files only if signals clearly apply.
5. Align existing files with required headings (see rules/alignment.md).
6. Mark unknown sections as `N/A` or `Pending`.
7. Verify/create/modify agent instructions files if applicable.
   - Use `.github/skills/ai-context-bootstrap/templates/agents_instructions/` as reference.
   - Paths:
     - `.github/copilot-instructions.md`
     - `/AGENTS.md` (if not exist, create in project root, not in `.github/`)
   - Ensure consistency with `.ai-context/README.md`.
   - Ensure instructions follow language policy.
   - Add or update language rules if missing.
8. Produce a final report.

## Minimal questions policy

Ask at most **3 questions**, and only if blocked.
Valid reasons to ask:

- Project type is ambiguous
- Runtime or entry point is required and missing
- Deployment target is required and missing

Never ask questions “just in case”.

## Output format

Always return:

### Summary

- Detected signals
- Files created or updated
- Files suggested but not created

### Checklist

- [x] Completed actions
- [ ] Pending actions

### Questions

Only if required to continue.

## Standard reference

This skill follows:

- `.ai-context/` standard v1
- Provider-agnostic rules
- Human-readable, IDE-first workflow
