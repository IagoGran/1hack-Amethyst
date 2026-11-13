# MVP Implementation Plan

This plan turns the requirements in `project_requirements.md` into owned tasks and subtasks for three contributors. Requirement IDs remain the source of truth. A listed task is planned work, not evidence that the behavior is implemented.

## Branches and Ownership

Use `dev` as the integration branch for the three long-running workstream branches, confirmed by the project owner on 2026-11-13. S0 is implemented on `feature/contracts` and merged into `dev` after validation. Preserve existing branches with other names.

| Contributor | Workstream | Branch | Primary ownership |
|---|---|---|---|
| Iago (Person A) | Desktop experience and user-facing state | `feature/mvp-desktop` | Desktop window, chat, settings, conversations, skills, approval/status presentation, accessibility |
| Hugo (Person B) | Agent, permissions, execution, and safety | `feature/mvp-agent-security` | Task orchestration, permissions, approval enforcement, code-workspace operations, sandbox, limits, retention/credential enforcement |
| Antonio (Person C) | Providers, connectors, and persistence foundations | `feature/mvp-integrations` | Provider/tool contracts, model and data adapters, connection configuration and health checks, persistence adapters, adapter contract tests |

Iago owns Person A / Workstream A, Hugo owns Person B / Workstream B, and Antonio owns Person C / Workstream C. The three contributors should agree on interface contracts in the first integration PR. Each workstream owns its implementation and tests; a shared-file change affecting another workstream needs an agreed contract and a small coordinated PR. Avoid simultaneous edits to shared context or requirements files; the workstream author making a consequential decision updates the relevant context with that PR.

## Shared Setup and Parallel Branch Workflow

### S0. Establish the integration baseline — all contributors, before feature work

- [x] Confirm the integration branch and create the three branches in the table. `dev` is confirmed; all three local branches were created from the tested S0 baseline.
- [x] Review the existing skeleton and identify current interfaces, launch path, persistence, and test commands. See `s0_contract_baseline.md`.
- [x] Turn the pending implementation choices below into small contract proposals; do not silently treat the proposals here as approved architecture. Concrete interface proposals and bounded technology evaluations are in `s0_contract_baseline.md`.
- [ ] Agree on minimal contracts and placeholder implementations for desktop-to-application calls, model providers, tools, approvals, task events, persistence, and sandbox invocation.
- [ ] Merge the contract-only PR first. Rebase or merge it into all three workstream branches before implementing against it.
- [x] Record contract decisions in the relevant `.ai-context/` guides. Leave undecided technology as `Pending`.

S0 code is implemented: async ports, shared task/event/request/result types, deterministic fakes, detached in-memory repositories, memory credentials, deny-all approvals, and a disabled sandbox. The Python package is now `amethyst`; the distribution and CLI remain `1hack-amethyst`. Contributor acknowledgment of these reviewable proposals remains **Pending**; no approval from absent contributors is asserted. Hosted PR creation/review remains **Pending** GitHub access. The tested baseline commit `950c770` was merged locally into `dev`, and all three planned workstream branches were created from it, under the owner's explicit instruction. No remote push or hosted PR merge has occurred. The two process checkboxes remain open rather than being reported as completed PR/team review.

### Branch operation

- Keep each PR focused on its workstream and requirement IDs. Prefer small PRs from each branch to the integration branch.
- Sync each workstream branch from the integration branch after shared-contract and prerequisite PRs merge.
- Do not make one workstream branch depend on unmerged commits from another. If coordination needs a temporary combined build, use an integration branch; keep both source branches independently mergeable.
- Publish interface changes in a contract PR before dependent work proceeds. Include a stub/fake so other contributors can keep working.
- Run the critical-path and adapter checks applicable to the PR. The release gate remains the full section 5.8 test gate in `project_requirements.md`.

## Workstream A — Desktop Experience

Branch: `feature/mvp-desktop`

### A1. Desktop shell and platform launch — FR-01, FR-03, section 5.1

- [ ] Select and document a desktop framework and packaging approach; validate it can launch on Ubuntu 24.04 x86-64 and through Windows 11 WSL2 GUI.
- [ ] Add the standalone application window and application lifecycle.
- [ ] Add navigation/layout for chat, conversations, settings, skills, permissions, and task details.
- [ ] Add launch smoke tests for both target environments.

### A2. Chat and task interaction — FR-01, FR-02, FR-05, FR-08, FR-12, FR-18, NFR-02

- [ ] Build message entry, transcript display, streaming response rendering, and errors.
- [ ] Show running, paused-for-budget, completed, cancelled, and failed task states with useful progress updates.
- [ ] Add cancellation UI and show when cancellation takes effect.
- [ ] Support code-generation and supplied-error/debugging workflows through application contracts.
- [ ] Keep the interface responsive during generation and tool execution; measure status-feedback target from section 5.5.

### A3. Conversation history — FR-04

- [ ] Add conversation list and open/resume actions.
- [ ] Add delete action and clear feedback.
- [ ] Connect to persistence contract; verify conversations remain until deleted and can be resumed after app restart.

### A4. Unified settings and connections UI — FR-03, FR-19, FR-21, FR-22, FR-24

- [ ] Add model/provider configuration and model ID entry for OpenAI, Gemini, DeepSeek, and Ollama.
- [ ] Add SQL connection forms for SQLite 3 and PostgreSQL 16+.
- [ ] Add locally hosted Qdrant, Milvus, and ChromaDB settings and Brave Search API settings.
- [ ] Support add, edit, enable, disable, test, and understandable connection failure states.
- [ ] Use secrets-entry controls that do not echo or expose credential values.

### A5. Approval and action transparency UI — FR-15, FR-27, FR-29, FR-30, NFR-14, NFR-15

- [ ] Present proposed file diffs before edits and identify the exact action(s) in an approval request.
- [ ] Support one-action approval and explicit batch approval; require renewed review when the proposal changes.
- [ ] Present deny, revoke, waiting, completed, and failed states accurately.
- [ ] Explain high-impact actions in user-understandable language.

### A6. Skills interface — FR-32, FR-33, FR-34

- [ ] Create, view, edit, enable, disable, and delete saved skills.
- [ ] Allow explicit skill selection and show when configured skill conditions activate one.
- [ ] Connect to skill application and persistence contracts.

### A7. Accessibility and UI acceptance — NFR-16, sections 5.1, 5.5, 5.7, 5.8

- [ ] Support keyboard navigation and accessible labels on interactive controls.
- [ ] Show explicit budget pauses, truncated results, timeout outcomes, and temporary-data behavior where user action is required.
- [ ] Add smoke coverage for chat, settings, approvals, conversation history, and sandbox results on both supported platforms.
- [ ] Measure UI status feedback and record results against section 5.5.

## Workstream B — Agent, Permissions, Execution, and Safety

Branch: `feature/mvp-agent-security`

### B1. Task lifecycle and orchestration — FR-05 through FR-11, NFR-08 through NFR-10

- [ ] Model task states, progress events, cancellation, and budget-paused state.
- [ ] Inspect relevant task context and detect already-started or partially completed work.
- [ ] Plan multi-step work before consequential actions; select enabled tools through contracts.
- [ ] Inspect tool results, validate outcomes, and decide whether more work is needed.
- [ ] Recover from transient tool failures within retry limits; report permanent failures and stop safely.
- [ ] Keep displayed task, permission, and result state consistent with execution outcomes.
- [ ] Keep the application usable and communicate limitations during provider/connector outages.

### B2. Workspace code operations — FR-13 through FR-15, FR-18, FR-26, FR-27

- [ ] Implement scoped workspace inspection after permission is granted.
- [ ] Generate a meaningful diff for file changes, including new-file previews as appropriate.
- [ ] Bind approval to the reviewed diff and relevant file state; invalidate approval when either changes.
- [ ] Apply approved changes only; record outcome and report failure without claiming success.
- [ ] Analyze supplied failures and connect proposed/implemented fixes to the same permission and diff-review path.

### B3. Permission and approval engine — FR-26 through FR-30, NFR-05, NFR-15

- [ ] Define permission scopes for tools and local resources with grant, inspect, and revoke operations.
- [ ] Scope protected approval to one action or explicitly enumerated action/diff batch.
- [ ] Expire action approvals after use or task completion; expire read-only session grants on app exit.
- [ ] Enforce high-impact approval for destructive actions and database writes.
- [ ] Block protected execution when permission is absent, expired, or revoked, including unexecuted batch actions.
- [ ] Add tests for approval denial, expiry, revocation, batch scope, and changed-diff invalidation.

### B4. Sandboxed commands and tests — FR-16, FR-17, NFR-06

- [ ] Choose and document a container runtime and threat boundary; validate the choice on Ubuntu and WSL2 before relying on it.
- [ ] Restrict mounted/writable paths to the approved workspace and deny network access by default.
- [ ] Require explicit authorization for the requested command/test scope; do not permit host-local command execution.
- [ ] Enforce cancellation and the 120-second command timeout; collect bounded output and exit status.
- [ ] Prevent uncertain command outcomes from triggering automatic re-execution.
- [ ] Test workspace escape attempts, network denial, cancellation, timeout, output limits, and approval enforcement.

### B5. Budget, timeout, and retry controls — FR-08, FR-11, NFR-01, NFR-03

- [ ] Enforce per-task token budget, per-request input/output limits, model context capacity, retrieval limits, row limits, and output-byte limits from section 5.6.
- [ ] Pause and report when the task budget is reached; continue only after explicit user increase.
- [ ] Enforce provider/tool, model idle/total, command, and total task deadlines from section 5.5.
- [ ] Retry only transient failures, at most twice after initial attempt, using exponential backoff with jitter and provider retry guidance.
- [ ] Never automatically retry permission/auth/input failures or mutations/commands with uncertain outcomes.
- [ ] Mark truncated results and terminal timeout state clearly for the UI.

### B6. Retention, credentials, and logging — FR-28, FR-31, NFR-04, NFR-07

- [ ] Integrate the OS credential store; use memory-only credentials when unavailable and never persist plaintext fallback.
- [ ] Redact secrets from errors/logs and exclude prompts, source, queries, and tool-result bodies from normal logs.
- [ ] Delete raw retrieval and workspace copies at task end unless explicitly saved; do not delete user project/source data.
- [ ] Expire redacted diagnostic logs after seven days and support explicit permanent saving/deletion.
- [ ] Coordinate persisted conversation content with Workstream C; ordinary logs do not implement the later FR-31 action-history interface.
- [ ] Test secret redaction, fallback, expiry, explicit log saving, and temporary-data cleanup.

### B7. Automated critical paths — NFR-12, section 5.8

- [ ] Add deterministic tests for task transitions, cancellation, permissions, SQL read-only enforcement, sandbox policy, budgets, timeouts, retries, and state consistency.
- [ ] Track aggregate branch coverage across domain, application, and security modules; reach at least 80%.
- [ ] Coordinate adapter contract and desktop smoke tests with Workstreams A and C.

## Workstream C — Providers, Connectors, and Persistence Foundations

Branch: `feature/mvp-integrations`

### C1. Shared integration contracts — FR-09, FR-19 through FR-25, NFR-11

- [ ] Agree and publish model-provider, tool/connector, connection-test, source-attribution, and error contracts before adapter implementation.
- [ ] Keep adapters behind ports; do not couple orchestration or desktop code to a vendor SDK.
- [ ] Provide fake adapters/fixtures so other branches can work without live services or credentials.
- [ ] Define how connection secrets are passed from the credential service without entering ordinary configuration exports/logs.

### C2. Model providers — FR-02, FR-03, FR-09, FR-24, FR-35

- [ ] Implement OpenAI API adapter with streaming where supported.
- [ ] Implement Gemini API adapter with streaming where supported.
- [ ] Implement DeepSeek API adapter with streaming where supported.
- [ ] Implement local Ollama adapter with streaming where supported.
- [ ] Support configured model IDs; report provider capabilities, connection errors, and usage needed by budget enforcement.
- [ ] Add adapter contract tests using fakes/recorded fixtures; keep live-service tests opt-in.
- [ ] General model parameter configuration beyond model selection remains a later requirement (FR-35).

### C3. External SQL connectors — FR-19, FR-20, FR-23, FR-24

- [ ] Implement SQLite 3 connection and read-only query adapter.
- [ ] Implement PostgreSQL 16+ connection and read-only query adapter.
- [ ] Enforce read-only access at the database/connection boundary as well as query validation.
- [ ] Enforce row and output limits; preserve useful column/source metadata and report truncation.
- [ ] Add deterministic contract tests for successful reads, writes rejected, timeouts, limits, and failures.

### C4. Web and vector connectors — FR-21 through FR-24

- [ ] Implement Brave Search API connector with bounded results and source URLs.
- [ ] Implement locally hosted Qdrant connector.
- [ ] Implement locally hosted Milvus connector.
- [ ] Implement locally hosted ChromaDB connector.
- [ ] Enforce retrieval/output limits and preserve source/resource identifiers where available.
- [ ] Add deterministic connector contract tests and opt-in live connection checks.

### C5. Connection configuration and credential integration — FR-03, FR-24, NFR-04, NFR-13

- [ ] Define validated, secret-free connection configuration formats for the selected providers/stores.
- [ ] Support add/edit/enable/disable/test states through application contracts.
- [ ] Integrate with Workstream B's OS credential-store interface and memory-only fallback.
- [ ] Ensure exported configuration excludes plaintext secrets; portable import/export as a full product feature remains Later (NFR-13).

### C6. Conversation and skill persistence — FR-04, FR-32, FR-33

- [ ] Propose and agree on the internal persistence engine and conversation/skill repository contracts; these choices remain `Pending` until approved.
- [ ] Persist conversations until deletion and support list/load/resume/delete operations.
- [ ] Persist skills and support create/read/update/delete and enabled state.
- [ ] Provide deterministic repository tests, including app-restart conversation recovery.
- [ ] Coordinate conversation schema/events with Workstream A; coordinate raw-content cleanup with Workstream B.

### C7. Adapter testing and resilience — FR-10, FR-11, NFR-08, NFR-09, NFR-11, NFR-12

- [ ] Provide contract tests for every approved model provider, SQL engine, vector store, and search provider.
- [ ] Verify unavailable providers fail clearly and recover without corrupting task state.
- [ ] Verify result/error translation, cancellation propagation where supported, deadlines, and bounded output.
- [ ] Keep tests deterministic and credential-free by default; document opt-in live-service setup.

## Requirement Coverage Index

Every functional and non-functional requirement ID appears in one or more owned tasks above.

| Requirements | Primary owner |
|---|---|
| FR-01–FR-05 | A (UI); B (cancellation/task lifecycle); C (conversation persistence) |
| FR-06–FR-11 | B; C provides adapter contracts and failures |
| FR-12–FR-18 | A (presentation); B (code operations, sandbox, execution) |
| FR-19–FR-25 | A (settings); C (adapters and contracts); B enforces authorized execution and limits |
| FR-26–FR-31 | B (authorization and safety); A (approval UI); C (connector/credential integration) |
| FR-32–FR-35 | A (skills/model UI); B (skill application); C (persistence/providers) |
| NFR-01–NFR-03 | B (budget and time enforcement); A (responsive status); C (provider usage/capabilities) |
| NFR-04–NFR-07 | B (security controls); C (credential and adapter integration); A (safe presentation) |
| NFR-08–NFR-10 | B (task/failure state); C (adapter behavior); A (status display) |
| NFR-11–NFR-13 | C (modular contracts/config); B (tests/security); NFR-13 portability remains Later |
| NFR-14–NFR-16 | A (clarity, transparency, accessibility); B (accurate states) |

## Integration Order and Cross-Branch Dependencies

1. **Contract baseline (S0):** settle minimum ports/events/repository shapes and desktop-to-application boundary; merge stubs/fakes.
2. **Vertical skeletons:** A launches shell with fake application service; B runs task/approval state tests with fake tools; C passes contract tests with fake providers. These can proceed in parallel after S0.
3. **Foundational integrations:** merge C persistence and provider/tool adapters as small independent PRs; B consumes tool/provider contracts and adds policy enforcement; A consumes the application events and persistence service.
4. **Protected actions and sandbox:** B's approval and sandbox interfaces land before A wires approval UI and before commands/tests are exposed through settings/chat.
5. **End-to-end MVP:** integrate selected providers/connectors, conversation/skill persistence, settings, permissions, and task display; run section 5.8 gate across both target environments.
6. **Acceptance and release:** record section 5.5 benchmark environments/results and resolve any failing acceptance checks before calling the MVP complete.

## Open Implementation Decisions

These affect implementation but were not fixed by the requirements answers. Decide them in S0 or the owning task and update context with the decision:

- Desktop GUI framework, application packaging and WSL2 GUI launch approach (A).
- Container runtime and enforceable sandbox profile on Ubuntu and WSL2 (B).
- Internal database, migrations, local data encryption/backup design, and cleanup scheduling (C with B for retention).
- Exact supported model IDs, API SDKs, and connector versions (C).
- Reference machines, representative models, benchmark fixtures, and how p95 is measured (A/B/C together).
- Contributor names and integration branch name are resolved: Iago (A), Hugo (B), Antonio (C), and `dev`. Separate contributor acknowledgment of the S0 contract proposals remains Pending.
