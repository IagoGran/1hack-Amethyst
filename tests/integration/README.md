# Integration Tests

External services must be explicitly configured; never use real credentials by default.

`test_agent_sandbox.py` composes the production `AgentService`, approval engine, and Docker sandbox with a deterministic provider and daemon double. It checks that the desktop-facing approval stream gates container creation, nonzero exits reach the provider as tool results, and uncertain execution fails the task without retry. Run it with `uv run pytest tests/integration/test_agent_sandbox.py`.

`test_live_sandbox.py` is opt-in real-container acceptance. It skips by default and fails on configuration/runtime errors after opt-in. See [runtime profile and commands](../../docs/sandbox_runtime.md). It does not require provider credentials or an external network service.

## Workstream A/C handoff

The following checks remain Pending until the desktop and real adapters are integrated. This table is an executable-contract handoff and acceptance checklist, not a claim that other contributors have reviewed or run it.

| Owner | Integration check | Expected evidence |
|---|---|---|
| A + B | Display `ApprovalRequest.actions` exactly, including command and network scope; grant, deny, and revoke via trusted user controls. | No execution on denial/revocation; changed action requires new review. Use `test_agent_sandbox.py` as the event consumer example. |
| A + B | Cancel an active sandbox command; show timeout, nonzero exit, truncation, and uncertain cleanup accurately. | UI remains responsive; cancellation is acknowledged after cleanup; no false success or automatic command retry. |
| A + B | Run desktop chat, settings, approvals, conversations, and sandbox smoke workflows on both approved platforms. | Recorded OS/Windows build, Docker/image profile, GUI results, and visible status timing. |
| B + C | Supply provider/tool bindings with usage, cancellation, errors, and bounded results through existing ports. | Contract tests for all four model providers, both SQL engines, all three vector stores, and Brave. Read-only SQL must also be enforced by the database connection. |
| B + C | Inject durable conversation/skill repositories and OS credentials; close the application session. | Restart/resume/delete works; temporary data is removed; read grants expire; secrets never enter ordinary output or configuration. |
| A + B + C | Validate Secret Service availability and memory-only fallback on native Ubuntu and WSL2. | No plaintext fallback and no credentials surviving a memory-only session restart. |

The existing provisional launcher smoke test does not establish desktop acceptance. Deterministic fakes do not establish live-adapter or durable-storage acceptance.
